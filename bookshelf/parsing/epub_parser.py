"""EPUB parsing with ebooklib + BeautifulSoup (spine order, nav TOC)."""

from __future__ import annotations

from bs4 import BeautifulSoup
from ebooklib import epub
import ebooklib

from .base import DocumentParser, SegmentBuilder
from .segments import HEADING, PARAGRAPH, LIST_ITEM, QUOTE, CAPTION


_TAG_KIND = {
    "p": (PARAGRAPH, None),
    "li": (LIST_ITEM, None),
    "blockquote": (QUOTE, None),
    "figcaption": (CAPTION, None),
    "h1": (HEADING, 1),
    "h2": (HEADING, 2),
    "h3": (HEADING, 3),
    "h4": (HEADING, 4),
    "h5": (HEADING, 5),
    "h6": (HEADING, 6),
}


class EpubParser(DocumentParser):
    def parse(self):
        book = epub.read_epub(self.local_path)
        builder = SegmentBuilder()

        # Map item href -> chapter title from the EPUB nav/TOC.
        toc_titles = self._flatten_toc(book.toc)

        first_chapter_opened = False
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            href = item.get_name()
            soup = BeautifulSoup(item.get_content(), "lxml")
            body = soup.body or soup

            title = toc_titles.get(href) or toc_titles.get(href.split("#")[0])
            if title:
                builder.add_chapter(title, level=1)
                first_chapter_opened = True

            for tag in body.find_all(list(_TAG_KIND.keys())):
                # Skip list items handled inside nested structures twice.
                text = tag.get_text(" ", strip=True)
                if not text:
                    continue
                kind, level = _TAG_KIND[tag.name]
                if kind == HEADING and not first_chapter_opened:
                    builder.add_chapter(text, level=level or 1)
                    first_chapter_opened = True
                builder.add(text, kind=kind, level=level)

        return builder.result()

    @staticmethod
    def _flatten_toc(toc) -> dict[str, str]:
        """Flatten the (possibly nested) ebooklib TOC into href -> title."""
        result: dict[str, str] = {}

        def walk(entries):
            for entry in entries:
                if isinstance(entry, (tuple, list)):
                    walk(entry)
                elif isinstance(entry, epub.Link):
                    result[entry.href] = entry.title
                    result[entry.href.split("#")[0]] = entry.title

        walk(toc)
        return result
