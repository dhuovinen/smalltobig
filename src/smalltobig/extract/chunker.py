"""Chunk normalized text at ~800 words with ~100 word overlap.

Sized in words rather than tokens — no tokenizer dependency for something
that's only ever an approximate context-window budget (docs/PLAN.md §2
Stage 2). Each chunk is a literal slice of the source text, never a
rejoin of split tokens, so it is guaranteed to already be a substring of
the normalized text the verify gate checks against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WORD = re.compile(r"\S+")

DEFAULT_CHUNK_WORDS = 800
DEFAULT_OVERLAP_WORDS = 100


@dataclass(frozen=True)
class Chunk:
    index: int
    start: int
    end: int
    text: str


def chunk_text(
    normalized: str,
    *,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[Chunk]:
    if chunk_words <= overlap_words:
        raise ValueError("chunk_words must exceed overlap_words")

    words = list(_WORD.finditer(normalized))
    if not words:
        return []

    step = chunk_words - overlap_words
    chunks = []
    index = 0
    i = 0
    while True:
        window = words[i : i + chunk_words]
        start, end = window[0].start(), window[-1].end()
        chunks.append(Chunk(index=index, start=start, end=end, text=normalized[start:end]))
        if i + chunk_words >= len(words):
            break
        i += step
        index += 1
    return chunks
