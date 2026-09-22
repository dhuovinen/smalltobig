"""Source: raw.txt + sha256, immutable. See docs/PLAN.md §2 Stage 1.

Raw bytes are never rewritten. Normalization writes a second file
(normalized.txt) alongside the original, and every downstream claim span
indexes into that normalized text, never into the raw bytes.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class SourceKind(StrEnum):
    PAPER = "paper"
    BOOK_EXCERPT = "book_excerpt"
    ARTICLE = "article"
    TALK_TRANSCRIPT = "talk_transcript"
    PODCAST_TRANSCRIPT = "podcast_transcript"
    NOTES = "notes"


class Source(BaseModel):
    id: str
    title: str
    author: str | None = None
    kind: SourceKind
    url: str | None = None
    retrieved_at: datetime
    sha256: str
    license_note: str | None = None
    original_filename: str | None = None


def slugify(title: str, *, max_words: int = 4) -> str:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return "-".join(words[:max_words]) or "untitled"


def generate_source_id(title: str, sha256: str) -> str:
    return f"src_{slugify(title)}_{sha256[:8]}"
