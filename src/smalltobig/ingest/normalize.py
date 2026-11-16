"""Text normalization: dehyphenate, collapse whitespace.

Claim spans (Stage 2) index into this output, never into raw bytes — see
docs/PLAN.md §2 Stage 1. Subtitle-specific markup stripping lives in
ingest/subtitles.py and calls back into this module.
"""

from __future__ import annotations

import re

_HYPHEN_LINEBREAK = re.compile(r"(\w)-\n(\w)")
_INLINE_WHITESPACE = re.compile(r"[ \t]+")
_BLANK_LINE_RUN = re.compile(r"\n{3,}")


def dehyphenate(text: str) -> str:
    """Join a word split across a line break by a hyphen: "exam-\\nple" ->
    "example". PDF text extraction produces these at every line wrap."""
    return _HYPHEN_LINEBREAK.sub(r"\1\2", text)


def collapse_whitespace(text: str) -> str:
    lines = [_INLINE_WHITESPACE.sub(" ", line).strip() for line in text.splitlines()]
    collapsed = "\n".join(lines)
    return _BLANK_LINE_RUN.sub("\n\n", collapsed)


def normalize_plain_text(text: str) -> str:
    return collapse_whitespace(dehyphenate(text)).strip()
