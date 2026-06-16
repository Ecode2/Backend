"""Pluggable Text-to-Speech provider interface.

Speed is *not* baked into synthesis (``speaking_rate`` stays 1.0); the frontend
changes playback speed via ``playbackRate`` so speed changes never re-bill.
"""

from __future__ import annotations

import html
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings

from ..parsing.normalize import split_sentences


@dataclass
class SynthesisResult:
    audio: bytes
    duration_ms: int
    encoding: str


class TTSService(ABC):
    encoding = "MP3"

    @abstractmethod
    def synthesize(self, text: str, voice: str, language: str | None = None) -> SynthesisResult:
        """Synthesize ``text`` with ``voice`` and return audio bytes + duration."""
        raise NotImplementedError

    def list_voices(self, language: str | None = None) -> list[dict]:
        """Return available voices. Providers may override; default is empty."""
        return []

    # -- shared helpers --------------------------------------------------
    def build_ssml(self, text: str, is_heading: bool = False) -> str:
        """Wrap text in SSML: sentences in <s>, breaks/emphasis on headings."""
        sentences = split_sentences(text) or [text]
        body = "".join(f"<s>{html.escape(s)}</s>" for s in sentences)
        if is_heading:
            return f'<speak><emphasis level="moderate">{body}</emphasis>' \
                   f'<break time="500ms"/></speak>'
        return f"<speak>{body}</speak>"

    def chunk_text(self, text: str, max_bytes: int | None = None) -> list[str]:
        """Split text into sub-requests under the provider input byte limit."""
        max_bytes = max_bytes or getattr(settings, "TTS_MAX_INPUT_BYTES", 4500)
        if len(text.encode("utf-8")) <= max_bytes:
            return [text]
        chunks, current = [], ""
        for sentence in split_sentences(text) or [text]:
            candidate = f"{current} {sentence}".strip()
            if len(candidate.encode("utf-8")) > max_bytes and current:
                chunks.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def probe_duration_ms(audio: bytes, encoding: str = "MP3") -> int:
        """Best-effort duration from encoded audio bytes via mutagen."""
        try:
            from mutagen import File as MutagenFile

            fobj = io.BytesIO(audio)
            parsed = MutagenFile(fobj)
            if parsed and parsed.info and getattr(parsed.info, "length", None):
                return int(parsed.info.length * 1000)
        except Exception:
            pass
        # Fallback: assume ~16 kbps so the scrubber still advances.
        return int(len(audio) / (16000 / 8) * 1000) if audio else 0
