"""Compress raw PCM into a streamable, browser-decodable container.

Providers that return raw PCM (NVIDIA/Riva) would otherwise ship WAV over the
WebSocket at ~88 KB/s for 44.1 kHz 16-bit mono, which dominates time-to-first
-audio on mobile. Encoding to MP3 cuts that by roughly 15x.

MP3 is the default deliberately: the reader decodes frames with the Web Audio
API's ``decodeAudioData()``, and MP3 is the one lossy format every target
browser -- crucially iOS Safari -- decodes reliably. Ogg/Opus is smaller still
but Safari's support for it in Web Audio is patchy.
"""

from __future__ import annotations

import functools
import logging
import shutil
import struct
import subprocess

logger = logging.getLogger(__name__)

# encoding name -> (ffmpeg args, file extension)
# The output muxer must be named explicitly for every codec: writing to
# "pipe:1" gives ffmpeg no filename extension to infer the format from, and it
# aborts with "Unable to choose an output format for 'pipe:1'".
_CODECS = {
    "MP3": (["-c:a", "libmp3lame", "-f", "mp3"], "mp3"),
    "OGG_OPUS": (["-c:a", "libopus", "-f", "ogg"], "ogg"),
    "AAC": (["-c:a", "aac", "-f", "adts"], "aac"),
}


@functools.lru_cache(maxsize=1)
def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def wav_header(pcm_len: int, sample_rate: int, channels: int = 1, width: int = 2) -> bytes:
    """Minimal 44-byte RIFF/WAVE header for signed 16-bit little-endian PCM."""
    byte_rate = sample_rate * channels * width
    return b"".join([
        b"RIFF", struct.pack("<I", 36 + pcm_len), b"WAVEfmt ",
        struct.pack("<I", 16), struct.pack("<H", 1),
        struct.pack("<H", channels), struct.pack("<I", sample_rate),
        struct.pack("<I", byte_rate), struct.pack("<H", channels * width),
        struct.pack("<H", width * 8), b"data", struct.pack("<I", pcm_len),
    ])


def encode_pcm(
    pcm: bytes,
    sample_rate: int,
    encoding: str = "MP3",
    bitrate: str = "48k",
    channels: int = 1,
) -> tuple[bytes, str]:
    """Return ``(audio_bytes, actual_encoding)`` for raw 16-bit PCM.

    Falls back to WAV when the container is unknown or ffmpeg is unavailable,
    so a missing binary degrades bandwidth rather than breaking playback.
    """
    encoding = (encoding or "WAV").upper()
    if encoding == "WAV" or encoding not in _CODECS:
        if encoding not in _CODECS and encoding != "WAV":
            logger.warning("Unsupported TTS encoding %r; falling back to WAV.", encoding)
        return wav_header(len(pcm), sample_rate, channels) + pcm, "WAV"

    exe = ffmpeg_path()
    if not exe:
        logger.warning(
            "ffmpeg not found; serving uncompressed WAV. Install ffmpeg to cut "
            "reader bandwidth by roughly 15x."
        )
        return wav_header(len(pcm), sample_rate, channels) + pcm, "WAV"

    codec_args, _ = _CODECS[encoding]
    cmd = [
        exe, "-hide_banner", "-loglevel", "error",
        "-f", "s16le", "-ar", str(sample_rate), "-ac", str(channels), "-i", "pipe:0",
        *codec_args, "-b:a", bitrate, "-ac", str(channels), "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, input=pcm, capture_output=True, check=True)
        if proc.stdout:
            return proc.stdout, encoding
        logger.warning("ffmpeg produced no output; falling back to WAV.")
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "ffmpeg failed (%s); falling back to WAV. stderr=%s",
            exc.returncode, (exc.stderr or b"")[:400].decode("utf-8", "replace"),
        )
    except Exception:
        logger.exception("ffmpeg invocation failed; falling back to WAV.")
    return wav_header(len(pcm), sample_rate, channels) + pcm, "WAV"
