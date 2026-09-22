from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from smalltobig.config import Settings
from smalltobig.ingest.paste import DuplicateSourceError, ingest_pasted_text
from smalltobig.models.source import SourceKind
from smalltobig.store import db, repo_sources

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]


@pytest.fixture
def conn(settings: Settings) -> Iterator[sqlite3.Connection]:
    connection = db.connect(settings.db_path)
    yield connection
    connection.close()


def test_ingest_pasted_text_writes_raw_and_normalized_files(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    source = ingest_pasted_text(
        conn,
        settings,
        text="Hello   world.",
        title="A Test Source",
        kind=SourceKind.NOTES,
    )

    raw = repo_sources.raw_path(settings, source.id, ".txt")
    normalized = repo_sources.normalized_path(settings, source.id)
    assert raw.read_text(encoding="utf-8") == "Hello   world."
    assert normalized.read_text(encoding="utf-8") == "Hello world."


def test_ingest_pasted_text_stores_a_retrievable_record(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    source = ingest_pasted_text(
        conn,
        settings,
        text="Some content.",
        title="Recorded Source",
        kind=SourceKind.ARTICLE,
        author="Jane Doe",
        url="https://example.com/article",
        license_note="fair use excerpt",
    )

    fetched = repo_sources.get(conn, source.id)
    assert fetched is not None
    assert fetched.title == "Recorded Source"
    assert fetched.author == "Jane Doe"
    assert fetched.url == "https://example.com/article"
    assert fetched.license_note == "fair use excerpt"


def test_ingest_pasted_text_rejects_duplicate_content(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    ingest_pasted_text(conn, settings, text="Same text.", title="First", kind=SourceKind.NOTES)

    with pytest.raises(DuplicateSourceError) as exc_info:
        ingest_pasted_text(
            conn, settings, text="Same text.", title="Second", kind=SourceKind.NOTES
        )
    assert exc_info.value.existing.title == "First"
