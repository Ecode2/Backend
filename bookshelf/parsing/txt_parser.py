"""Plain-text parsing: blank-line paragraphs, tolerant chapter detection."""

from __future__ import annotations

import re

from .base import DocumentParser, SegmentBuilder
from .segments import HEADING, PARAGRAPH


_CHAPTER_RE = re.compile(
    r"^\s*(chapter|part|book|section)\s+([\divxlcdm]+|\w+)\b.*$",
    re.IGNORECASE,
)


class TxtParser(DocumentParser):
    def parse(self):
        builder = SegmentBuilder()
        with open(self.local_path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()

        # Form-feed marks a hard page/chapter break in many plain-text books.
        chunks = raw.split("\f")
        for chunk in chunks:
            paragraphs = re.split(r"\n\s*\n", chunk)
            for para in paragraphs:
                text = para.strip()
                if not text:
                    continue
                first_line = text.splitlines()[0].strip()
                if self._is_chapter_heading(first_line):
                    builder.add_chapter(first_line, level=1)
                    builder.add(first_line, kind=HEADING, level=1)
                    rest = text[len(first_line):].strip()
                    if rest:
                        builder.add(rest, kind=PARAGRAPH)
                else:
                    builder.add(text, kind=PARAGRAPH)

        return builder.result()

    @staticmethod
    def _is_chapter_heading(line: str) -> bool:
        if len(line) > 80:
            return False
        return bool(_CHAPTER_RE.match(line))
