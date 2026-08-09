"""NVIDIA (Riva) Text-to-Speech provider.

NVIDIA's hosted TTS models on the API catalog (build.nvidia.com), e.g. the
Magpie-TTS family, are served over gRPC rather than a REST/JSON API -- there
is no OpenAI-style ``/v1/audio/speech`` endpoint. Each model is selected by a
"function-id" (a UUID shown on that model's build.nvidia.com page) plus a
voice name, so switching models means changing ``NVIDIA_TTS_FUNCTION_ID`` (and
usually ``TTS_DEFAULT_VOICE``), not a single "model" string.

Requires the ``nvidia-riva-client`` package.
"""

from __future__ import annotations

import functools

from django.conf import settings

from .base import TTSService, SynthesisResult

DEFAULT_NVCF_SERVER = "grpc.nvcf.nvidia.com:443"


@functools.lru_cache(maxsize=8)
def _service(server: str, use_ssl: bool, api_key: str, function_id: str):
    import riva.client

    metadata = [["function-id", function_id], ["authorization", f"Bearer {api_key}"]]
    auth = riva.client.Auth(None, use_ssl, server, metadata)
    return riva.client.SpeechSynthesisService(auth)


class NvidiaTTSService(TTSService):
    # Riva returns a proper Ogg/Opus container for OGGOPUS, unlike LINEAR_PCM
    # which is headerless raw PCM -- OGG_OPUS lets storage/probing/playback
    # work unchanged.
    encoding = "OGG_OPUS"

    def __init__(self):
        self.server = getattr(settings, "NVIDIA_TTS_SERVER", DEFAULT_NVCF_SERVER)
        self.use_ssl = bool(getattr(settings, "NVIDIA_TTS_USE_SSL", True))
        self.api_key = getattr(settings, "NVIDIA_API_KEY", "")
        self.function_id = getattr(settings, "NVIDIA_TTS_FUNCTION_ID", "")
        self.sample_rate_hz = int(getattr(settings, "NVIDIA_TTS_SAMPLE_RATE_HZ", 44100))

    def _client(self):
        if not self.api_key:
            raise RuntimeError("NVIDIA_API_KEY is not configured.")
        if not self.function_id:
            raise RuntimeError(
                "NVIDIA_TTS_FUNCTION_ID is not configured. Pick a TTS model on "
                "build.nvidia.com and copy its function-id."
            )
        return _service(self.server, self.use_ssl, self.api_key, self.function_id)

    def synthesize(self, text, voice, language=None):
        import riva.client

        language = language or getattr(settings, "TTS_DEFAULT_LANGUAGE", "en-US")
        service = self._client()

        audio = b""
        for chunk in self.chunk_text(text):
            resp = service.synthesize(
                chunk,
                voice_name=voice,
                language_code=language,
                encoding=riva.client.AudioEncoding.OGGOPUS,
                sample_rate_hz=self.sample_rate_hz,
            )
            audio += resp.audio

        return SynthesisResult(
            audio=audio,
            duration_ms=self.probe_duration_ms(audio, self.encoding),
            encoding=self.encoding,
        )

    def list_voices(self, language=None):
        # SpeechSynthesisService has no list-voices RPC; NVIDIA publishes each
        # model's voice roster on its build.nvidia.com model card.
        return []
