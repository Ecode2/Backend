"""Semantic document parsing layer.

Public API:

    from bookshelf.parsing import get_parser, parse_document, Segment, TocEntry

``parse_document`` returns ``(segments, toc)`` as lists of dataclasses. Views
and consumers should use :class:`~bookshelf.models.DocumentStructure` to cache
the serialized result rather than re-parsing on every access.
"""

from __future__ import annotations

from .base import DocumentParser, PARSER_VERSION
from .segments import Segment, TocEntry, estimate_duration_ms
from .pdf_parser import PdfParser
from .epub_parser import EpubParser
from .docx_parser import DocxParser
from .txt_parser import TxtParser


_PARSERS: dict[str, type[DocumentParser]] = {
    "pdf": PdfParser,
    "epub": EpubParser,
    "docx": DocxParser,
    "txt": TxtParser,
}

SUPPORTED_DOCUMENT_FORMATS = set(_PARSERS)


def get_parser(local_path: str, fmt: str) -> DocumentParser:
    fmt = (fmt or "").lower().lstrip(".")
    parser_cls = _PARSERS.get(fmt)
    if parser_cls is None:
        raise ValueError(f"Unsupported document format: {fmt!r}")
    return parser_cls(local_path)


def parse_document(local_path: str, fmt: str) -> tuple[list[Segment], list[TocEntry]]:
    return get_parser(local_path, fmt).parse()


__all__ = [
    "DocumentParser",
    "PARSER_VERSION",
    "Segment",
    "TocEntry",
    "estimate_duration_ms",
    "get_parser",
    "parse_document",
    "SUPPORTED_DOCUMENT_FORMATS",
]
