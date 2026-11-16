from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from smalltobig.models.field_note import Debrief
from smalltobig.store import db, repo_debriefs

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path

NOW = datetime(2026, 9, 22, tzinfo=UTC)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def test_create_and_get_round_trip(conn: sqlite3.Connection) -> None:
    debrief = Debrief(id="dbf_1", text="It went well.", created_at=NOW)
    repo_debriefs.create(conn, debrief)
    assert repo_debriefs.get(conn, "dbf_1") == debrief


def test_get_missing_returns_none(conn: sqlite3.Connection) -> None:
    assert repo_debriefs.get(conn, "does-not-exist") is None
