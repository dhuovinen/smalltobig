from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from smalltobig.config import Settings
from smalltobig.ingest.watchfolder import poll_inbox, scan_inbox
from smalltobig.store import db, repo_sources

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]
    s.inbox_dir.mkdir(parents=True)
    return s


@pytest.fixture
def conn(settings: Settings) -> Iterator[sqlite3.Connection]:
    connection = db.connect(settings.db_path)
    yield connection
    connection.close()


def test_scan_inbox_lists_supported_files_only(settings: Settings) -> None:
    (settings.inbox_dir / "notes.txt").write_text("hi", encoding="utf-8")
    (settings.inbox_dir / "cover.jpg").write_bytes(b"\x00")
    (settings.inbox_dir / ".DS_Store").write_bytes(b"\x00")

    found = scan_inbox(settings)
    assert [p.name for p in found] == ["notes.txt"]


def test_scan_inbox_on_missing_directory_returns_empty(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "nope")  # type: ignore[call-arg]
    assert scan_inbox(settings) == []


def test_poll_inbox_ingests_and_moves_files(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    (settings.inbox_dir / "my-notes.txt").write_text("Some notes.", encoding="utf-8")

    ingested = poll_inbox(conn, settings)

    assert len(ingested) == 1
    source = ingested[0]
    assert source.title == "my-notes"
    assert source.original_filename == "my-notes.txt"
    assert not (settings.inbox_dir / "my-notes.txt").exists()
    assert repo_sources.raw_path(settings, source.id, ".txt").read_text(
        encoding="utf-8"
    ) == "Some notes."
    assert scan_inbox(settings) == []


def test_poll_inbox_quarantines_duplicate_content_without_a_second_record(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    (settings.inbox_dir / "first.txt").write_text("Same content.", encoding="utf-8")
    first_batch = poll_inbox(conn, settings)
    assert len(first_batch) == 1

    (settings.inbox_dir / "duplicate.txt").write_text("Same content.", encoding="utf-8")
    second_batch = poll_inbox(conn, settings)

    assert second_batch == []
    assert len(repo_sources.list_all(conn)) == 1
    assert not (settings.inbox_dir / "duplicate.txt").exists()
    assert (settings.sources_dir / "_duplicates" / "duplicate.txt").exists()
