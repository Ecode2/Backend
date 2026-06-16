"""Text normalization applied to every parsed segment.

Goal: clean text that reads well both visually (Apple Books feel) and aloud
(Google TTS). v1 keeps display and TTS text identical.
"""

from __future__ import annotations

import re
import unicodedata


# Control chars except tab/newline.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Word split across a line break with a hyphen: "exam-\nple" -> "example".
_HYPHEN_BREAK_RE = re.compile(r"(\w)[­-]\s*\n\s*(\w)")
_MULTI_WS_RE = re.compile(r"[ \t ]+")
_MULTI_NL_RE = re.compile(r"\n{2,}")

_QUOTE_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-",
    "…": "...",
    " ": " ",
}


def normalize_text(text: str) -> str:
    """Collapse whitespace, repair hyphenated breaks, strip control chars."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)
    for src, dst in _QUOTE_MAP.items():
        text = text.replace(src, dst)
    text = _CONTROL_RE.sub("", text)
    # Join intra-paragraph line wraps into single spaces, keep nothing else.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTI_NL_RE.sub("\n", text)
    text = text.replace("\n", " ")
    text = _MULTI_WS_RE.sub(" ", text)
    return text.strip()


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def split_sentences(text: str) -> list[str]:
    """Lightweight sentence splitter for SSML and sub-request chunking."""
    text = text.strip()
    if not text:
        return []
    parts = _SENTENCE_RE.split(text)
    return [p.strip() for p in parts if p.strip()]
