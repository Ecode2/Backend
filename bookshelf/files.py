"""File helpers: format detection, checksums, and leak-free temp copies.

Replaces the old per-request ``_get_pdf_path`` that downloaded the file on
every page request and never cleaned up the ``NamedTemporaryFile``.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile

DOCUMENT_FORMATS = {"pdf", "epub", "docx", "txt"}
AUDIO_FORMATS = {"mp3", "m4a", "m4b", "aac", "ogg", "opus", "wav", "flac"}

_EXT_ALIASES = {"text": "txt"}


def detect_format(filename: str) -> str:
    """Best-effort format from the file extension, normalized."""
    ext = os.path.splitext(filename or "")[1].lower().lstrip(".")
    ext = _EXT_ALIASES.get(ext, ext)
    return ext


def is_audio_format(fmt: str) -> bool:
    return (fmt or "").lower() in AUDIO_FORMATS


def is_document_format(fmt: str) -> bool:
    return (fmt or "").lower() in DOCUMENT_FORMATS


def compute_checksum(file_obj) -> str:
    """SHA-256 of a Django file/field, streamed so large files don't blow RAM."""
    hasher = hashlib.sha256()
    file_obj.open("rb") if hasattr(file_obj, "open") else None
    try:
        file_obj.seek(0)
    except (AttributeError, ValueError):
        pass
    for chunk in file_obj.chunks() if hasattr(file_obj, "chunks") else iter(
        lambda: file_obj.read(8192), b""
    ):
        hasher.update(chunk)
    try:
        file_obj.seek(0)
    except (AttributeError, ValueError):
        pass
    return hasher.hexdigest()


@contextlib.contextmanager
def local_copy(file_field, suffix: str = ""):
    """Yield a local filesystem path for a (possibly remote) storage file.

    Downloads once into a NamedTemporaryFile and **always** deletes it on exit,
    even on error. Use as::

        with local_copy(book_file.file, suffix=".pdf") as path:
            parse(path)
    """
    if not suffix:
        name = getattr(file_field, "name", "") or ""
        ext = os.path.splitext(name)[1]
        suffix = ext or ""

    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        file_field.open("rb")
        try:
            for chunk in file_field.chunks():
                tmp.write(chunk)
        finally:
            file_field.close()
        tmp.flush()
        tmp.close()
        yield tmp.name
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(tmp.name)
