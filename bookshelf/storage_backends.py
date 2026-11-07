"""S3-compatible storage backends (Cloudflare R2).

``MediaStorage`` holds uploaded book files and is the project ``default``
storage. ``AudioStorage`` holds synthesized TTS audio under a separate key
prefix so the audio cache can be lifecycle-managed independently.
"""

from storages.backends.s3 import S3Storage


class MediaStorage(S3Storage):
    """Uploaded documents and native audiobook files."""

    location = "media"
    file_overwrite = False


class AudioStorage(S3Storage):
    """Synthesized TTS audio segments (deduplicated cache)."""

    location = "audio"
    file_overwrite = True  # cache keys are content-addressed; overwrite is safe


def get_audio_storage():
    """Return the storage used for synthesized audio.

    Falls back to the project default storage when S3 is not configured (dev
    without a bucket), so audio still persists to the local filesystem.
    """
    from django.conf import settings

    if getattr(settings, "USE_S3", False):
        return AudioStorage()
    from django.core.files.storage import default_storage

    return default_storage
