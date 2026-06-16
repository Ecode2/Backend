"""Document/audiobook services: parse-and-cache structure, covers, audio probe.

These are synchronous and may do network + CPU work (download from storage,
parse, render). Call them from a thread executor / ``database_sync_to_async``
in the Channels consumer so the event loop is never blocked.
"""

from __future__ import annotations

import io
import logging

from django.core.files.base import ContentFile

from .files import local_copy
from .models import (
    AUDIOBOOK,
    DOCUMENT,
    AudioChapter,
    Book,
    BookFile,
    DocumentStructure,
)
from .parsing import PARSER_VERSION, parse_document, estimate_duration_ms
from .parsing.segments import Segment, TocEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Upload processing (synchronous; run off the request thread for big files)
# ---------------------------------------------------------------------------
def process_uploaded_file(book_file: BookFile) -> None:
    """Post-upload processing: set book type, parse/probe, generate cover.

    Best-effort — failures are logged but never break the upload response.
    """
    book = book_file.book
    try:
        if book_file.is_audio:
            if book.book_type != AUDIOBOOK:
                Book.objects.filter(pk=book.pk).update(book_type=AUDIOBOOK)
                book.book_type = AUDIOBOOK
            probe_audiobook(book)
        else:
            if book.book_type != DOCUMENT:
                Book.objects.filter(pk=book.pk).update(book_type=DOCUMENT)
            get_or_build_structure(book_file)
        generate_cover(book_file)
    except Exception:  # pragma: no cover - never fail the upload
        logger.exception("post-upload processing failed for %s", book_file)


# ---------------------------------------------------------------------------
# Document structure (parse once, cache)
# ---------------------------------------------------------------------------
def get_or_build_structure(book_file: BookFile, force: bool = False) -> DocumentStructure:
    """Return the cached parse for ``book_file``, building it if stale/missing."""
    structure = DocumentStructure.objects.filter(book_file=book_file).first()
    if (
        structure
        and not force
        and structure.parser_version == PARSER_VERSION
        and structure.checksum == (book_file.checksum or "")
    ):
        return structure

    segments, toc = _parse_file(book_file)
    seg_dicts = [s.to_dict() for s in segments]
    toc_dicts = [t.to_dict() for t in toc]

    structure, _ = DocumentStructure.objects.update_or_create(
        book_file=book_file,
        defaults={
            "segments": seg_dicts,
            "toc": toc_dicts,
            "parser_version": PARSER_VERSION,
            "checksum": book_file.checksum or "",
        },
    )

    _update_book_denormals(book_file.book, segments)
    return structure


def _parse_file(book_file: BookFile) -> tuple[list[Segment], list[TocEntry]]:
    fmt = book_file.fmt or "txt"
    with local_copy(book_file.file, suffix=f".{fmt}") as path:
        return parse_document(path, fmt)


def _update_book_denormals(book: Book, segments: list[Segment]) -> None:
    pages = {s.page for s in segments if s.page is not None}
    Book.objects.filter(pk=book.pk).update(
        total_segments=len(segments),
        total_page=max(pages) if pages else book.total_page,
        duration_estimate_ms=estimate_duration_ms(segments),
    )


def load_segments(structure: DocumentStructure) -> list[Segment]:
    return [Segment.from_dict(d) for d in structure.segments]


def load_toc(structure: DocumentStructure) -> list[TocEntry]:
    return [TocEntry.from_dict(d) for d in structure.toc]


def pages_from_structure(structure: DocumentStructure) -> dict[int, str]:
    """Reconstruct page -> text mapping (backward-compat for read-page/pages)."""
    pages: dict[int, list[str]] = {}
    for seg in structure.segments:
        page = seg.get("page")
        if page is None:
            continue
        pages.setdefault(page, []).append(seg.get("text", ""))
    return {page: "\n\n".join(parts) for page, parts in sorted(pages.items())}


def page_text(structure: DocumentStructure, page: int) -> str:
    parts = [
        seg.get("text", "")
        for seg in structure.segments
        if seg.get("page") == page
    ]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Cover art
# ---------------------------------------------------------------------------
def generate_cover(book_file: BookFile) -> str | None:
    """Render/extract a cover image, store it, and set ``book.cover_url``.

    PDF -> first page raster; audio -> embedded artwork (if any). Best-effort:
    returns the URL or ``None``.
    """
    try:
        if book_file.fmt == "pdf":
            data, content_type = _pdf_cover(book_file)
        elif book_file.is_audio:
            data, content_type = _audio_cover(book_file)
        else:
            return None
    except Exception:  # pragma: no cover - cover art is non-critical
        logger.exception("cover generation failed for %s", book_file)
        return None

    if not data:
        return None

    ext = "png" if content_type.endswith("png") else "jpg"
    name = f"books/{book_file.book_id}/cover.{ext}"
    saved = book_file.file.storage.save(name, ContentFile(data))
    url = book_file.file.storage.url(saved)
    Book.objects.filter(pk=book_file.book_id).update(cover_url=url)
    return url


def _pdf_cover(book_file: BookFile) -> tuple[bytes, str]:
    import fitz

    with local_copy(book_file.file, suffix=".pdf") as path:
        doc = fitz.open(path)
        try:
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            return pix.tobytes("png"), "image/png"
        finally:
            doc.close()


def _audio_cover(book_file: BookFile) -> tuple[bytes | None, str]:
    from mutagen import File as MutagenFile

    with local_copy(book_file.file, suffix=f".{book_file.fmt}") as path:
        audio = MutagenFile(path)
        if audio is None:
            return None, ""
        # ID3 APIC
        for key in getattr(audio, "tags", {}) or {}:
            if key.startswith("APIC"):
                return audio.tags[key].data, "image/jpeg"
        # MP4 cover atom
        covr = getattr(audio, "tags", {}) and audio.tags.get("covr")
        if covr:
            return bytes(covr[0]), "image/jpeg"
    return None, ""


# ---------------------------------------------------------------------------
# Native audiobook probing (durations + chapters)
# ---------------------------------------------------------------------------
def probe_audiobook(book: Book) -> None:
    """Populate per-track durations and chapter markers for an audiobook.

    Chapters come from embedded markers (m4b/ID3 chapters) when present, else
    each file becomes one chapter (file-boundary navigation).
    """
    if book.book_type != AUDIOBOOK:
        return

    files = list(book.files.order_by("order", "id"))
    AudioChapter.objects.filter(book=book).delete()

    chapter_index = 0
    elapsed_total = 0
    for f in files:
        duration_ms, markers = _probe_track(f)
        if duration_ms:
            BookFile.objects.filter(pk=f.pk).update(duration_ms=duration_ms)

        if markers:
            for title, start_ms, end_ms in markers:
                AudioChapter.objects.create(
                    book=book, book_file=f, index=chapter_index,
                    title=title, start_ms=start_ms, end_ms=end_ms,
                )
                chapter_index += 1
        else:
            AudioChapter.objects.create(
                book=book, book_file=f, index=chapter_index,
                title=f.track_title or f"Chapter {chapter_index + 1}",
                start_ms=0, end_ms=duration_ms or None,
            )
            chapter_index += 1
        elapsed_total += duration_ms or 0

    Book.objects.filter(pk=book.pk).update(
        duration_estimate_ms=elapsed_total,
        total_segments=chapter_index,
    )


def _probe_track(book_file: BookFile) -> tuple[int, list[tuple[str, int, int | None]]]:
    from mutagen import File as MutagenFile

    duration_ms = 0
    markers: list[tuple[str, int, int | None]] = []
    try:
        with local_copy(book_file.file, suffix=f".{book_file.fmt}") as path:
            audio = MutagenFile(path)
            if audio is None:
                return 0, []
            if audio.info and getattr(audio.info, "length", None):
                duration_ms = int(audio.info.length * 1000)

            chapters = getattr(audio, "chapters", None)
            if chapters:
                for i, ch in enumerate(chapters):
                    title = getattr(ch, "title", None) or f"Chapter {i + 1}"
                    start = int(getattr(ch, "start", 0) * 1000)
                    end = getattr(ch, "end", None)
                    markers.append((title, start, int(end * 1000) if end else None))
    except Exception:  # pragma: no cover
        logger.exception("audio probe failed for %s", book_file)
    return duration_ms, markers
