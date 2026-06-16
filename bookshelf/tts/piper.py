"""Local TTS provider using Piper (https://github.com/rhasspy/piper).

No cloud dependency or billing. Requires the ``piper`` binary and a voice model
on the VPS (configure ``PIPER_BINARY`` / ``PIPER_MODEL_PATH``). Outputs WAV.
"""

from __future__ import annotations

import subprocess
import tempfile
import os

from django.conf import settings

from .base import TTSService, SynthesisResult


class PiperTTSService(TTSService):
    encoding = "WAV"

    def __init__(self):
        self.binary = getattr(settings, "PIPER_BINARY", "piper")
        self.model = getattr(settings, "PIPER_MODEL_PATH", "")

    def synthesize(self, text, voice=None, language=None):
        if not self.model:
            raise RuntimeError("PIPER_MODEL_PATH is not configured.")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as out:
            out_path = out.name
        try:
            subprocess.run(
                [self.binary, "--model", self.model, "--output_file", out_path],
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
            )
            with open(out_path, "rb") as fh:
                audio = fh.read()
        finally:
            if os.path.exists(out_path):
                os.remove(out_path)
        return SynthesisResult(
            audio=audio,
            duration_ms=self.probe_duration_ms(audio, "WAV"),
            encoding=self.encoding,
        )

    def list_voices(self, language=None):
        name = os.path.basename(self.model) or "piper-local"
        return [{
            "name": name,
            "language_codes": [language or getattr(settings, "TTS_DEFAULT_LANGUAGE", "en-US")],
            "ssml_gender": "NEUTRAL",
        }]
