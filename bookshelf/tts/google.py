"""Google Cloud Text-to-Speech provider.

Auth uses Application Default Credentials. On a self-hosted VPS (no GCP metadata
server) set ``GOOGLE_APPLICATION_CREDENTIALS`` to a service-account key file.
"""

from __future__ import annotations

import functools

from django.conf import settings

from .base import TTSService, SynthesisResult


@functools.lru_cache(maxsize=1)
def _client():
    from google.cloud import texttospeech

    return texttospeech.TextToSpeechClient()


class GoogleTTSService(TTSService):
    def __init__(self):
        self.encoding = getattr(settings, "TTS_AUDIO_ENCODING", "MP3")

    def _audio_encoding(self):
        from google.cloud import texttospeech

        return {
            "MP3": texttospeech.AudioEncoding.MP3,
            "OGG_OPUS": texttospeech.AudioEncoding.OGG_OPUS,
        }.get(self.encoding, texttospeech.AudioEncoding.MP3)

    def synthesize(self, text, voice, language=None):
        from google.cloud import texttospeech

        language = language or getattr(settings, "TTS_DEFAULT_LANGUAGE", "en-US")
        client = _client()
        audio_config = texttospeech.AudioConfig(
            audio_encoding=self._audio_encoding(),
            speaking_rate=1.0,  # speed is client-side; never re-bill
            pitch=0.0,
        )
        voice_params = texttospeech.VoiceSelectionParams(
            language_code=language, name=voice
        )

        chunks = self.chunk_text(text)
        audio = b""
        for chunk in chunks:
            ssml = self.build_ssml(chunk)
            synthesis_input = texttospeech.SynthesisInput(ssml=ssml)
            resp = client.synthesize_speech(
                input=synthesis_input, voice=voice_params, audio_config=audio_config
            )
            audio += resp.audio_content

        return SynthesisResult(
            audio=audio,
            duration_ms=self.probe_duration_ms(audio, self.encoding),
            encoding=self.encoding,
        )

    def list_voices(self, language=None):
        from google.cloud import texttospeech

        client = _client()
        resp = client.list_voices(language_code=language) if language else client.list_voices()
        gender = texttospeech.SsmlVoiceGender
        out = []
        for v in resp.voices:
            out.append({
                "name": v.name,
                "language_codes": list(v.language_codes),
                "ssml_gender": gender(v.ssml_gender).name,
                "natural_sample_rate_hertz": v.natural_sample_rate_hertz,
            })
        return out
