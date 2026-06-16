"""Audio reader WebSocket consumer.

Protocol (authoritative spec, Section 9): each ``segment_meta`` text frame is
immediately followed by exactly one binary audio frame for that segment.

For TTS *documents* the server synthesizes/streams audio. For *native
audiobooks* the client plays the file URLs directly over HTTP; the consumer
only sends metadata and persists progress.
"""

from __future__ import annotations

import asyncio
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from .models import AUDIOBOOK, Book, ReaderSettings, ReadingProgress

logger = logging.getLogger(__name__)

PROGRESS_SAVE_EVERY = 5     # persist every N segments
LOOKAHEAD = 2               # segments to stay ahead of paced playback


class ReaderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.book_id = int(self.scope["url_route"]["kwargs"]["book_id"])
        self.user = self.scope.get("user")
        self.play_task: asyncio.Task | None = None
        self.position = 0
        self.voice = getattr(settings, "TTS_DEFAULT_VOICE", "en-US-Neural2-F")
        self.language = getattr(settings, "TTS_DEFAULT_LANGUAGE", "en-US")
        self.segments: list[dict] = []
        self.toc: list[dict] = []

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4401)
            return

        self.book = await self._load_book()
        if self.book is None:
            await self.close(code=4404)
            return

        settings_obj = await self._load_settings()
        if settings_obj:
            self.voice = settings_obj["voice_name"] or self.voice
            self.language = settings_obj["language_code"] or self.language

        resume = await self._load_progress()
        self.position = resume["segment_index"]

        await self.accept()

        if self.book.book_type == AUDIOBOOK:
            await self._send_json({
                "type": "ready",
                "book_type": "audiobook",
                "tracks": await self._load_tracks(),
                "toc": await self._load_audio_chapters(),
                "resume": resume,
            })
            return

        await self._load_structure()
        await self._send_json({
            "type": "ready",
            "book_type": "document",
            "total_segments": len(self.segments),
            "toc": self.toc,
            "voice": self.voice,
            "resume": resume,
        })

    async def disconnect(self, code):
        await self._cancel_play()
        await self._save_progress(self.position)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            msg = json.loads(text_data)
        except json.JSONDecodeError:
            await self._error("bad_request", "Invalid JSON.")
            return
        action = msg.get("action")
        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            await self._error("bad_request", f"Unknown action: {action}")
            return
        await handler(msg)

    # -- actions ---------------------------------------------------------
    async def _action_play(self, msg):
        if "voice" in msg and msg["voice"]:
            self.voice = msg["voice"]
        target = msg.get("segment_index", self.position)
        await self._start_stream(target)

    async def _action_resume(self, msg):
        await self._start_stream(self.position)

    async def _action_pause(self, msg):
        await self._cancel_play()
        await self._save_progress(self.position)
        await self._send_json({"type": "paused", "segment_index": self.position})

    async def _action_stop(self, msg):
        await self._cancel_play()
        await self._save_progress(self.position)
        await self._send_json({"type": "stopped", "segment_index": self.position})

    async def _action_seek(self, msg):
        target = int(msg.get("segment_index", self.position))
        await self._start_stream(target)

    async def _action_set_voice(self, msg):
        self.voice = msg.get("voice") or self.voice
        # Re-synthesize upcoming segments with the new voice (past stays cached).
        await self._send_json({"type": "voice_changed", "voice": self.voice})
        if self.play_task and not self.play_task.done():
            await self._start_stream(self.position)

    async def _action_set_speed(self, msg):
        # Speed is applied client-side via playbackRate; ack only.
        await self._send_json({"type": "speed_ack", "speed": msg.get("speed", 1.0)})

    async def _action_next_chapter(self, msg):
        target = self._chapter_start(self._current_chapter() + 1)
        if target is not None:
            await self._start_stream(target)

    async def _action_prev_chapter(self, msg):
        target = self._chapter_start(self._current_chapter() - 1)
        if target is not None:
            await self._start_stream(target)

    async def _action_save_progress(self, msg):
        # Used by the native-audiobook client to checkpoint its HTML5 position.
        self.position = int(msg.get("segment_index", self.position))
        await self._save_progress(
            self.position,
            audio_ms=int(msg.get("audio_ms", 0)),
            chapter_index=int(msg.get("chapter_index", self._current_chapter())),
        )
        await self._send_json({"type": "progress_saved", "segment_index": self.position})

    # -- streaming loop --------------------------------------------------
    async def _start_stream(self, start_index: int):
        await self._cancel_play()
        start_index = max(0, min(start_index, max(0, len(self.segments) - 1)))
        self.position = start_index
        self.play_task = asyncio.create_task(self._stream_from(start_index))

    async def _cancel_play(self):
        if self.play_task and not self.play_task.done():
            self.play_task.cancel()
            try:
                await self.play_task
            except asyncio.CancelledError:
                pass
        self.play_task = None

    async def _stream_from(self, start_index: int):
        try:
            prev_duration = 0.0
            for offset, index in enumerate(range(start_index, len(self.segments))):
                seg = self.segments[index]
                try:
                    meta = await self._synthesize(seg["text"])
                except Exception:
                    logger.exception("synthesis failed for segment %s", index)
                    await self._error("synthesis_failed", f"segment {index}")
                    return

                await self._send_json({
                    "type": "segment_meta",
                    "segment_index": index,
                    "chapter_index": seg.get("chapter_index", 0),
                    "page": seg.get("page"),
                    "text": seg["text"],
                    "kind": seg.get("kind", "paragraph"),
                    "duration_ms": meta["duration_ms"],
                })
                await self.send(bytes_data=meta["audio"])

                self.position = index
                if index % PROGRESS_SAVE_EVERY == 0:
                    await self._save_progress(index)
                    await self._send_json({"type": "progress_saved", "segment_index": index})

                # Pace so we stay ~LOOKAHEAD segments ahead, never flooding.
                if offset >= LOOKAHEAD and prev_duration > 0:
                    await asyncio.sleep(prev_duration)
                prev_duration = meta["duration_ms"] / 1000.0
            await self._save_progress(self.position)
            await self._send_json({"type": "ended", "segment_index": self.position})
        except asyncio.CancelledError:
            raise

    @database_sync_to_async
    def _synthesize(self, text):
        from .tts import synthesize_segment
        return synthesize_segment(text, self.voice, self.language)

    # -- chapter helpers -------------------------------------------------
    def _current_chapter(self) -> int:
        if not self.segments:
            return 0
        idx = min(self.position, len(self.segments) - 1)
        return self.segments[idx].get("chapter_index", 0)

    def _chapter_start(self, chapter_index: int):
        if chapter_index < 0 or chapter_index >= len(self.toc):
            return None
        return self.toc[chapter_index].get("start_segment", 0)

    # -- data loading (sync ORM in executor) -----------------------------
    @database_sync_to_async
    def _load_book(self):
        book = Book.objects.filter(pk=self.book_id).first()
        if not book:
            return None
        if book.status == "public" or book.user_id == self.user.id:
            return book
        return None

    @database_sync_to_async
    def _load_settings(self):
        s = ReaderSettings.objects.filter(user=self.user).first()
        if not s:
            return None
        return {"voice_name": s.voice_name, "language_code": s.language_code}

    @database_sync_to_async
    def _load_progress(self):
        p = ReadingProgress.objects.filter(user=self.user, book_id=self.book_id).first()
        if not p:
            return {"segment_index": 0, "char_offset": 0, "chapter_index": 0, "audio_ms": 0}
        return {
            "segment_index": p.segment_index,
            "char_offset": p.char_offset,
            "chapter_index": p.chapter_index,
            "audio_ms": p.audio_ms,
        }

    def _load_structure_sync(self):
        from . import services
        book_file = self.book.primary_file()
        structure = services.get_or_build_structure(book_file)
        return structure.segments, structure.toc

    async def _load_structure(self):
        self.segments, self.toc = await database_sync_to_async(self._load_structure_sync)()

    @database_sync_to_async
    def _load_tracks(self):
        tracks = []
        for f in self.book.files.order_by("order", "id"):
            try:
                url = f.file.url
            except Exception:
                url = None
            tracks.append({
                "id": f.id, "order": f.order, "title": f.track_title,
                "url": url, "duration_ms": f.duration_ms, "fmt": f.fmt,
            })
        return tracks

    @database_sync_to_async
    def _load_audio_chapters(self):
        return [
            {
                "index": c.index, "title": c.title, "start_ms": c.start_ms,
                "end_ms": c.end_ms, "book_file": c.book_file_id,
            }
            for c in self.book.audio_chapters.all()
        ]

    @database_sync_to_async
    def _save_progress(self, segment_index, audio_ms=0, chapter_index=None):
        total = max(1, self.book.total_segments or len(self.segments) or 1)
        seg = None
        if 0 <= segment_index < len(self.segments):
            seg = self.segments[segment_index]
        ReadingProgress.objects.update_or_create(
            user=self.user, book_id=self.book_id,
            defaults={
                "segment_index": segment_index,
                "chapter_index": chapter_index if chapter_index is not None
                else (seg.get("chapter_index", 0) if seg else 0),
                "page": seg.get("page") if seg else None,
                "percent": round(min(1.0, segment_index / total) * 100, 2),
                "audio_ms": audio_ms,
            },
        )

    # -- io helpers ------------------------------------------------------
    async def _send_json(self, payload):
        await self.send(text_data=json.dumps(payload))

    async def _error(self, code, detail=""):
        await self._send_json({"type": "error", "code": code, "detail": detail})
