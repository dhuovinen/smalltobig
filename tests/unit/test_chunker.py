from __future__ import annotations

import pytest

from smalltobig.extract.chunker import chunk_text


def test_empty_text_produces_no_chunks() -> None:
    assert chunk_text("") == []


def test_short_text_is_a_single_chunk() -> None:
    text = "one two three four five"
    chunks = chunk_text(text, chunk_words=800, overlap_words=100)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].start == 0
    assert chunks[0].end == len(text)


def test_every_chunk_is_an_exact_substring_of_the_source() -> None:
    text = " ".join(f"word{i}" for i in range(50))
    chunks = chunk_text(text, chunk_words=10, overlap_words=2)
    for chunk in chunks:
        assert text[chunk.start : chunk.end] == chunk.text
        assert chunk.text in text


def test_chunks_overlap_by_the_configured_word_count() -> None:
    words = [f"w{i}" for i in range(30)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_words=10, overlap_words=3)

    assert len(chunks) > 1
    first_words = chunks[0].text.split()
    second_words = chunks[1].text.split()
    assert first_words[-3:] == second_words[:3]


def test_chunking_covers_every_word_exactly_once_at_minimum() -> None:
    words = [f"w{i}" for i in range(25)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_words=10, overlap_words=2)

    covered = set()
    for chunk in chunks:
        covered.update(chunk.text.split())
    assert covered == set(words)


def test_preserves_original_whitespace_within_a_chunk() -> None:
    text = "alpha  beta\ngamma"
    chunks = chunk_text(text, chunk_words=800, overlap_words=100)
    assert chunks[0].text == text


def test_rejects_overlap_not_smaller_than_chunk_size() -> None:
    with pytest.raises(ValueError, match="chunk_words must exceed overlap_words"):
        chunk_text("some text", chunk_words=10, overlap_words=10)
