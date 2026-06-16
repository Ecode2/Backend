"""DOCX parsing with python-docx (paragraph styles -> kinds, headings -> TOC)."""

from __future__ import annotations

import re

import docx

from .base import DocumentParser, SegmentBuilder
from .segments import HEADING, PARAGRAPH, LIST_ITEM, QUOTE


_HEADING_RE = re.compile(r"heading\s*([1-6])", re.IGNORECASE)


class DocxParser(DocumentParser):
    def parse(self):
        document = docx.Document(self.local_path)
        builder = SegmentBuilder()

        for para in document.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            style_name = (para.style.name if para.style else "") or ""

            heading_match = _HEADING_RE.search(style_name)
            if heading_match:
                level = int(heading_match.group(1))
                builder.add_chapter(text, level=level)
                builder.add(text, kind=HEADING, level=level)
            elif style_name.lower().startswith("title"):
                builder.add_chapter(text, level=1)
                builder.add(text, kind=HEADING, level=1)
            elif "list" in style_name.lower():
                builder.add(text, kind=LIST_ITEM)
            elif "quote" in style_name.lower():
                builder.add(text, kind=QUOTE)
            else:
                builder.add(text, kind=PARAGRAPH)

        return builder.result()
