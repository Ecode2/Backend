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
import logging

from django.conf import settings

from .base import TTSService, SynthesisResult
from .encode import encode_pcm

logger = logging.getLogger(__name__)

DEFAULT_NVCF_SERVER = "grpc.nvcf.nvidia.com:443"


# gRPC defaults to a 4 MB receive limit. LINEAR_PCM at 44.1 kHz mono 16-bit is
# ~86 KB/s, so that ceiling is reached after only ~48 seconds of speech -- one
# long paragraph -- and the RPC dies with RESOURCE_EXHAUSTED. Raise it clear of
# anything a single segment can produce.
MAX_GRPC_RECEIVE_BYTES = 64 * 1024 * 1024

# Riva caps offline synthesis at roughly 2000 *normalized* characters per
# request. Stay under that with headroom, because normalization expands text
# ("Dr." -> "Doctor", "1994" -> "nineteen ninety four").
MAX_CHARS_PER_REQUEST = 1500


@functools.lru_cache(maxsize=8)
def _service(server: str, use_ssl: bool, api_key: str, function_id: str):
    import riva.client

    metadata = [["function-id", function_id], ["authorization", f"Bearer {api_key}"]]
    auth = riva.client.Auth(
        None, use_ssl, server, metadata,
        options=[("grpc.max_receive_message_length", MAX_GRPC_RECEIVE_BYTES)],
    )
    return riva.client.SpeechSynthesisService(auth)


class NvidiaTTSService(TTSService):
    # Riva's OGGOPUS is NOT an Ogg container: it returns a bare sequence of
    # length-prefixed Opus packets ("<I" length + packet, repeated), which
    # browsers cannot feed to decodeAudioData() -- the reader silently dropped
    # every frame. So request LINEAR_PCM and compress it ourselves (see
    # tts/encode.py); MP3 keeps iOS Safari working while cutting the ~88 KB/s
    # that uncompressed WAV cost.

    # Riva emits 16-bit signed little-endian mono for LINEAR_PCM.
    SAMPLE_WIDTH_BYTES = 2
    CHANNELS = 1

    def __init__(self):
        self.server = getattr(settings, "NVIDIA_TTS_SERVER", DEFAULT_NVCF_SERVER)
        self.use_ssl = bool(getattr(settings, "NVIDIA_TTS_USE_SSL", True))
        self.api_key = getattr(settings, "NVIDIA_API_KEY", "")
        self.function_id = getattr(settings, "NVIDIA_TTS_FUNCTION_ID", "")
        self.sample_rate_hz = int(getattr(settings, "NVIDIA_TTS_SAMPLE_RATE_HZ", 44100))
        # Resolved per instance so the container can be changed via settings
        # without editing code; encode_pcm() downgrades to WAV if it cannot
        # honour the request (e.g. ffmpeg missing).
        self.encoding = getattr(settings, "TTS_AUDIO_ENCODING", "MP3").upper()
        self.bitrate = getattr(settings, "TTS_AUDIO_BITRATE", "48k")
        # Two independent limits protect two different failures: Riva's input
        # cap, and the gRPC message ceiling on the audio coming back.
        self.max_chars_per_request = min(
            int(getattr(settings, "TTS_MAX_INPUT_BYTES", 4500)),
            MAX_CHARS_PER_REQUEST,
        )

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

        # Concatenate raw PCM across chunks and encode once: stitching several
        # finished containers together would embed headers mid-stream.
        pcm = b""
        for chunk in self.chunk_text(text, max_bytes=self.max_chars_per_request):
            resp = service.synthesize(
                chunk,
                voice_name=voice,
                language_code=language,
                encoding=riva.client.AudioEncoding.LINEAR_PCM,
                sample_rate_hz=self.sample_rate_hz,
            )
            pcm += resp.audio

        # Duration comes from the PCM, so it stays exact regardless of the
        # container we ship (and never needs probing).
        frames = len(pcm) // (self.SAMPLE_WIDTH_BYTES * self.CHANNELS)
        duration_ms = int(frames * 1000 / self.sample_rate_hz) if self.sample_rate_hz else 0

        audio, actual = encode_pcm(
            pcm, self.sample_rate_hz, self.encoding, self.bitrate, self.CHANNELS
        )
        # Reflect what we actually produced: the cache key includes the
        # encoding, so claiming MP3 while serving WAV would poison it.
        self.encoding = actual
        return SynthesisResult(audio=audio, duration_ms=duration_ms, encoding=actual)

    # -- voice catalogue -------------------------------------------------
    # The gRPC SpeechSynthesisService has no list-voices RPC, but each NVCF
    # function exposes a small REST endpoint that does.
    VOICES_URL_TEMPLATE = "https://{function_id}.invocation.api.nvcf.nvidia.com/v1/audio/list_voices"

    @staticmethod
    def parse_voice_name(name: str) -> dict:
        """Split "Magpie-Multilingual.EN-US.Mia.Calm" into its parts.

        Riva encodes model, locale, speaker and (optionally) emotion into the
        voice id itself, which is the only place that metadata exists.
        """
        parts = name.split(".")
        model = parts[0] if parts else ""
        locale = parts[1] if len(parts) > 1 else ""
        speaker = parts[2] if len(parts) > 2 else ""
        emotion = parts[3] if len(parts) > 3 else ""
        # "EN-US" -> "en-US" (BCP-47), which is what the rest of the app uses.
        language_code = ""
        if "-" in locale:
            lang, _, region = locale.partition("-")
            language_code = f"{lang.lower()}-{region.upper()}"
        elif locale:
            language_code = locale.lower()
        return {
            "name": name,
            "model": model,
            "language_code": language_code,
            "speaker": speaker,
            # No emotion suffix means the model's default delivery.
            "emotion": emotion or "Default",
        }

    def list_voices(self, language=None):
        import requests

        if not self.api_key or not self.function_id:
            return []
        url = self.VOICES_URL_TEMPLATE.format(function_id=self.function_id)
        try:
            resp = requests.get(
                url, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=20
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            logger.exception("Could not list NVIDIA voices from %s", url)
            return []

        # Shape: {"<comma,separated,locales>": {"voices": [name, ...]}}
        names: list[str] = []
        for group in payload.values():
            if isinstance(group, dict):
                names.extend(group.get("voices") or [])
            elif isinstance(group, list):
                names.extend(group)

        voices = []
        for name in names:
            info = self.parse_voice_name(name)
            voices.append({
                "name": info["name"],
                "language_codes": [info["language_code"]] if info["language_code"] else [],
                # NVIDIA does not publish a gender for these voices; the useful
                # axis here is speaker + emotion, so report gender as unknown
                # rather than inventing one.
                "ssml_gender": "UNSPECIFIED",
                "speaker": info["speaker"],
                "emotion": info["emotion"],
                "model": info["model"],
            })

        if language:
            wanted = language.lower()
            voices = [
                v for v in voices
                if any(code.lower() == wanted or code.lower().startswith(wanted.split("-")[0])
                       for code in v["language_codes"])
            ]
        return sorted(voices, key=lambda v: (v["language_codes"], v["speaker"], v["emotion"]))
