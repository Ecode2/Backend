"""TTS facade: provider factory + deduplicated audio cache.

``synthesize_segment`` is the single entrypoint used by the consumer and any
REST path. It is content-addressed: identical (text, voice, encoding) is
synthesized once, stored, and reused forever.
"""

from __future__ import annotations

import functools
import hashlib
import logging

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from ..models import AudioSegmentCache
from ..storage_backends import get_audio_storage
from .base import TTSService

logger = logging.getLogger(__name__)

_PROVIDERS = {
    "nvidia": "bookshelf.tts.nvidia.NvidiaTTSService",
    "google": "bookshelf.tts.google.GoogleTTSService",
    "piper": "bookshelf.tts.piper.PiperTTSService",
    "dummy": "bookshelf.tts.dummy.DummyTTSService",
}


@functools.lru_cache(maxsize=1)
def get_tts_service() -> TTSService:
    from django.utils.module_loading import import_string

    provider = getattr(settings, "TTS_PROVIDER", "nvidia")
    path = _PROVIDERS.get(provider, _PROVIDERS["nvidia"])
    return import_string(path)()


def _cache_key(text: str, voice: str, encoding: str) -> str:
    return hashlib.sha256(f"{text}|{voice}|{encoding}".encode("utf-8")).hexdigest()


def _ext_for(encoding: str) -> str:
    return {"MP3": "mp3", "OGG_OPUS": "ogg", "WAV": "wav"}.get(encoding, "mp3")


def synthesize_segment(text: str, voice: str, language: str | None = None) -> dict:
    """Return cached/synthesized audio metadata for a segment.

    Returns a dict: ``{cache_key, url, duration_ms, byte_size, encoding, audio}``.
    ``audio`` (bytes) is always included so the consumer can stream a binary
    frame without a second round trip to storage.
    """
    service = get_tts_service()
    encoding = service.encoding
    key = _cache_key(text, voice, encoding)

    cached = AudioSegmentCache.objects.filter(cache_key=key).first()
    if cached:
        AudioSegmentCache.objects.filter(pk=cached.pk).update(
            last_accessed_at=timezone.now()
        )
        audio = _read_storage(cached.storage_path)
        return {
            "cache_key": key,
            "url": cached.storage_url,
            "duration_ms": cached.duration_ms,
            "byte_size": cached.byte_size,
            "encoding": cached.encoding,
            "audio": audio,
        }

    result = service.synthesize(text, voice, language)
    storage = get_audio_storage()
    path = f"tts/{key}.{_ext_for(encoding)}"
    saved_path = storage.save(path, ContentFile(result.audio))
    try:
        url = storage.url(saved_path)
    except Exception:
        url = saved_path

    AudioSegmentCache.objects.update_or_create(
        cache_key=key,
        defaults={
            "storage_url": url,
            "storage_path": saved_path,
            "duration_ms": result.duration_ms,
            "byte_size": len(result.audio),
            "voice": voice,
            "encoding": encoding,
            "last_accessed_at": timezone.now(),
        },
    )
    return {
        "cache_key": key,
        "url": url,
        "duration_ms": result.duration_ms,
        "byte_size": len(result.audio),
        "encoding": encoding,
        "audio": result.audio,
    }


def _read_storage(path: str) -> bytes:
    storage = get_audio_storage()
    try:
        with storage.open(path, "rb") as fh:
            return fh.read()
    except Exception:
        logger.exception("failed reading cached audio %s", path)
        return b""


__all__ = ["get_tts_service", "synthesize_segment"]
