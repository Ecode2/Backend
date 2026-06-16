"""Dummy TTS provider for local dev / tests without cloud credentials.

Returns a small silent MP3 frame so the audio pipeline and WS protocol can be
exercised end-to-end offline.
"""

from __future__ import annotations

from .base import TTSService, SynthesisResult

# A single silent MPEG-1 Layer III frame (very small, decodable by browsers).
_SILENT_MP3_FRAME = bytes.fromhex(
    "fffb9064000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000000000000000000000000000000000000000000000000"
)


class DummyTTSService(TTSService):
    encoding = "MP3"

    def synthesize(self, text, voice=None, language=None):
        # Scale length roughly with word count so the scrubber advances.
        frames = max(1, len(text.split()))
        audio = _SILENT_MP3_FRAME * frames
        return SynthesisResult(audio=audio, duration_ms=frames * 120, encoding="MP3")

    def list_voices(self, language=None):
        return [
            {"name": "dummy-voice-a", "language_codes": ["en-US"], "ssml_gender": "FEMALE"},
            {"name": "dummy-voice-b", "language_codes": ["en-US"], "ssml_gender": "MALE"},
        ]
