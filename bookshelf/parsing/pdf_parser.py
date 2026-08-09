"""PDF parsing with PyMuPDF: font-size heuristics for headings, outline TOC."""

from __future__ import annotations

from collections import Counter

import pymupdf

from .base import DocumentParser, SegmentBuilder
from .segments import HEADING, PARAGRAPH, LIST_ITEM


class PdfParser(DocumentParser):
    def parse(self):
        doc = pymupdf.open(self.local_path)
        try:
            return self._parse(doc)
        finally:
            doc.close()

    def _parse(self, doc):
        builder = SegmentBuilder()

        # 1. Collect block text + dominant font size per block, per page.
        pages_blocks: list[list[tuple[str, float, bool]]] = []
        size_counter: Counter[float] = Counter()
        for page in doc:
            blocks = []
            data = page.get_text("dict")
            for block in data.get("blocks", []):
                if block.get("type") != 0:
                    continue  # skip images
                lines = block.get("lines", [])
                text_parts, sizes, bold = [], [], False
                for line in lines:
                    for span in line.get("spans", []):
                        span_text = span.get("text", "")
                        if span_text.strip():
                            text_parts.append(span_text)
                            sizes.append(round(span.get("size", 0), 1))
                            if span.get("flags", 0) & 16:  # bold flag
                                bold = True
                text = " ".join(text_parts).strip()
                if not text:
                    continue
                size = max(set(sizes), key=sizes.count) if sizes else 0.0
                size_counter[size] += len(text)
                blocks.append((text, size, bold))
            pages_blocks.append(blocks)

        # 2. Body font size = most common by character weight; larger -> heading.
        body_size = size_counter.most_common(1)[0][0] if size_counter else 12.0
        heading_sizes = sorted(
            {s for s in size_counter if s > body_size * 1.12}, reverse=True
        )

        def heading_level(size: float, bold: bool) -> int | None:
            if size in heading_sizes:
                rank = heading_sizes.index(size)
                return min(rank + 1, 6)
            if bold and size >= body_size * 1.05:
                return 3
            return None

        # 3. Strip repeated headers/footers (same short line on most pages).
        repeated = self._repeated_edge_lines(pages_blocks)

        # 4. Seed TOC from the PDF outline if present.
        outline = doc.get_toc(simple=True)  # [[level, title, page], ...]
        outline_by_page: dict[int, list[tuple[int, str]]] = {}
        for level, title, page_no in outline:
            outline_by_page.setdefault(page_no, []).append((level, title))

        for page_index, blocks in enumerate(pages_blocks):
            page_no = page_index + 1
            for level, title in outline_by_page.get(page_no, []):
                builder.add_chapter(title, level=min(level, 6), page=page_no)
            for text, size, bold in blocks:
                if text.strip() in repeated:
                    continue
                level = heading_level(size, bold)
                if level is not None and len(text) < 200:
                    # Headings detected from font become chapters when no
                    # outline supplied one for this page.
                    if not outline_by_page:
                        builder.add_chapter(text, level=level, page=page_no)
                    builder.add(text, kind=HEADING, level=level, page=page_no)
                else:
                    kind = LIST_ITEM if self._looks_like_list(text) else PARAGRAPH
                    builder.add(text, kind=kind, page=page_no)

        return builder.result()

    @staticmethod
    def _looks_like_list(text: str) -> bool:
        stripped = text.lstrip()
        return bool(stripped) and stripped[0] in {"•", "-", "*", "◦", "▪"}

    @staticmethod
    def _repeated_edge_lines(pages_blocks) -> set[str]:
        """Lines appearing near the top/bottom of most pages = running heads."""
        if len(pages_blocks) < 4:
            return set()
        top, bottom = Counter(), Counter()
        for blocks in pages_blocks:
            if not blocks:
                continue
            first = blocks[0][0].strip()
            last = blocks[-1][0].strip()
            if len(first) < 80:
                top[first] += 1
            if len(last) < 80:
                bottom[last] += 1
        threshold = max(3, int(len(pages_blocks) * 0.5))
        repeated = {t for t, c in top.items() if c >= threshold}
        repeated |= {t for t, c in bottom.items() if c >= threshold}
        return repeated
