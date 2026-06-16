"""Abstract document parser and a small builder used by every subclass."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .segments import Segment, TocEntry, SEGMENT_KINDS, PARAGRAPH
from .normalize import normalize_text

# Bump when parsing logic changes meaningfully so cached structures re-parse.
PARSER_VERSION = 1


class SegmentBuilder:
    """Accumulates normalized segments and a TOC while parsing.

    Subclasses call :meth:`add_chapter` when a new top-level section starts and
    :meth:`add` for each text block. Empty/blank text is dropped automatically.
    """

    def __init__(self) -> None:
        self.segments: list[Segment] = []
        self.toc: list[TocEntry] = []
        self._chapter_index = -1

    def add_chapter(self, title: str, level: int = 1, page: int | None = None) -> int:
        title = normalize_text(title) or f"Section {len(self.toc) + 1}"
        self._chapter_index = len(self.toc)
        self.toc.append(
            TocEntry(
                index=self._chapter_index,
                title=title,
                level=level,
                start_segment=len(self.segments),
                page=page,
            )
        )
        return self._chapter_index

    def add(
        self,
        text: str,
        kind: str = PARAGRAPH,
        level: int | None = None,
        page: int | None = None,
    ) -> None:
        if kind not in SEGMENT_KINDS:
            kind = PARAGRAPH
        clean = normalize_text(text)
        if not clean:
            return
        if self._chapter_index < 0:
            # No explicit chapter yet — open an implicit one.
            self.add_chapter("Start", level=1, page=page)
        self.segments.append(
            Segment(
                index=len(self.segments),
                kind=kind,
                level=level,
                text=clean,
                chapter_index=self._chapter_index,
                page=page,
                char_count=len(clean),
            )
        )

    def result(self) -> tuple[list[Segment], list[TocEntry]]:
        if not self.toc and self.segments:
            self.toc.append(
                TocEntry(index=0, title="Start", level=1, start_segment=0, page=None)
            )
        return self.segments, self.toc


class DocumentParser(ABC):
    def __init__(self, local_path: str):
        self.local_path = local_path

    @abstractmethod
    def parse(self) -> tuple[list[Segment], list[TocEntry]]:
        """Return ordered segments and the table of contents."""
        raise NotImplementedError
