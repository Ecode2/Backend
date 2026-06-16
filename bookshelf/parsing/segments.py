"""Canonical position model shared by every format.

A parsed document is an ordered list of :class:`Segment` objects plus a list
of :class:`TocEntry` objects. The *segment index* is the canonical position
anchor: pages, chapters and percentages are all derived from it, which unifies
resume, bookmarks and progress across PDF / EPUB / DOCX / TXT.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


HEADING = "heading"
PARAGRAPH = "paragraph"
LIST_ITEM = "list_item"
QUOTE = "quote"
CAPTION = "caption"

SEGMENT_KINDS = {HEADING, PARAGRAPH, LIST_ITEM, QUOTE, CAPTION}


@dataclass
class Segment:
    index: int                      # 0-based, canonical position anchor
    kind: str                       # heading | paragraph | list_item | quote | caption
    level: Optional[int]            # heading level 1..6, else None
    text: str                       # clean, normalized text for TTS and display
    chapter_index: int              # which TOC entry this belongs to
    page: Optional[int]             # PDF page number, else None
    char_count: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Segment":
        return cls(
            index=data["index"],
            kind=data["kind"],
            level=data.get("level"),
            text=data["text"],
            chapter_index=data.get("chapter_index", 0),
            page=data.get("page"),
            char_count=data.get("char_count", len(data.get("text", ""))),
        )


@dataclass
class TocEntry:
    index: int
    title: str
    level: int
    start_segment: int              # first segment of this chapter/section
    page: Optional[int]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TocEntry":
        return cls(
            index=data["index"],
            title=data["title"],
            level=data.get("level", 1),
            start_segment=data.get("start_segment", 0),
            page=data.get("page"),
        )


def estimate_duration_ms(segments: list[Segment], words_per_minute: int = 155) -> int:
    """Rough spoken-duration estimate from word count (for the library shelf)."""
    words = sum(max(1, len(s.text.split())) for s in segments)
    if words == 0:
        return 0
    return int(words / words_per_minute * 60_000)
