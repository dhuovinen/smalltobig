from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from smalltobig.config import Settings
from smalltobig.models.source import Source, SourceKind
from smalltobig.store import db, repo_sources

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def _make_source(**overrides: object) -> Source:
    defaults: dict[str, object] = {
        "id": "src_example_deadbeef",
        "title": "Example",
        "author": "Someone",
        "kind": SourceKind.ARTICLE,
        "url": "https://example.com",
        "retrieved_at": datetime(2026, 9, 19, tzinfo=UTC),
        "sha256": "deadbeef" * 8,
        "license_note": None,
        "original_filename": None,
    }
    defaults.update(overrides)
    return Source(**defaults)  # type: ignore[arg-type]


def test_create_and_get_round_trip(conn: sqlite3.Connection) -> None:
    source = _make_source()
    repo_sources.create(conn, source, raw_extension=".txt")

    fetched = repo_sources.get(conn, source.id)
    assert fetched == source


def test_get_missing_returns_none(conn: sqlite3.Connection) -> None:
    assert repo_sources.get(conn, "does-not-exist") is None


def test_get_by_sha256_finds_duplicate_content(conn: sqlite3.Connection) -> None:
    source = _make_source()
    repo_sources.create(conn, source, raw_extension=".txt")

    assert repo_sources.get_by_sha256(conn, source.sha256) == source
    assert repo_sources.get_by_sha256(conn, "not-a-real-hash") is None


def test_list_all_orders_by_retrieved_at_descending(conn: sqlite3.Connection) -> None:
    older = _make_source(
        id="src_older_11111111",
        sha256="1" * 64,
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = _make_source(
        id="src_newer_22222222",
        sha256="2" * 64,
        retrieved_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    repo_sources.create(conn, older, raw_extension=".txt")
    repo_sources.create(conn, newer, raw_extension=".txt")

    assert [s.id for s in repo_sources.list_all(conn)] == [newer.id, older.id]


def test_raw_and_normalized_paths_are_derived_from_settings_and_id() -> None:
    settings = Settings(_env_file=None, data_dir=Path("/tmp/stb-data"))  # type: ignore[call-arg]
    assert repo_sources.raw_path(settings, "src_x", ".pdf") == Path(
        "/tmp/stb-data/sources/src_x/raw.pdf"
    )
    assert repo_sources.normalized_path(settings, "src_x") == Path(
        "/tmp/stb-data/sources/src_x/normalized.txt"
    )
