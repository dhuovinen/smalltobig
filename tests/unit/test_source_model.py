from __future__ import annotations

from smalltobig.models.source import generate_source_id, slugify


def test_slugify_keeps_first_few_words_lowercased() -> None:
    title = "It Doesn't Hurt to Ask: Question-Asking Increases Liking"
    assert slugify(title) == "it-doesn-t-hurt"


def test_slugify_falls_back_for_titles_with_no_word_characters() -> None:
    assert slugify("!!!") == "untitled"


def test_generate_source_id_combines_slug_and_hash_prefix() -> None:
    source_id = generate_source_id("Boomerasking", "abcdef0123456789")
    assert source_id == "src_boomerasking_abcdef01"
