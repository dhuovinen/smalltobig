from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from smalltobig.models.conflict import Conflict, ConflictStatus
from smalltobig.store import db, repo_conflicts

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def _make_conflict(**overrides: object) -> Conflict:
    defaults: dict[str, object] = {
        "id": "cfl_deadbeef",
        "between": ["rule-a", "rule-b"],
        "note": "They contradict.",
        "status": ConflictStatus.PROPOSED,
        "proposed_resolution": "Scope both.",
        "resolution": None,
        "created_at": datetime(2026, 9, 22, tzinfo=UTC),
        "resolved_at": None,
    }
    defaults.update(overrides)
    return Conflict(**defaults)  # type: ignore[arg-type]


def test_create_and_get_round_trip(conn: sqlite3.Connection) -> None:
    conflict = _make_conflict()
    repo_conflicts.create(conn, conflict)
    assert repo_conflicts.get(conn, conflict.id) == conflict


def test_get_by_pair_matches_regardless_of_order(conn: sqlite3.Connection) -> None:
    conflict = _make_conflict(between=["rule-a", "rule-b"])
    repo_conflicts.create(conn, conflict)

    assert repo_conflicts.get_by_pair(conn, "rule-a", "rule-b") == conflict
    assert repo_conflicts.get_by_pair(conn, "rule-b", "rule-a") == conflict


def test_get_by_pair_returns_none_when_no_conflict_recorded(conn: sqlite3.Connection) -> None:
    assert repo_conflicts.get_by_pair(conn, "rule-a", "rule-b") is None


def test_resolve_sets_status_resolution_and_timestamp(conn: sqlite3.Connection) -> None:
    repo_conflicts.create(conn, _make_conflict())
    resolved_at = datetime(2026, 9, 23, tzinfo=UTC)

    repo_conflicts.resolve(
        conn, "cfl_deadbeef", "Keep both, scoped differently.", resolved_at=resolved_at
    )

    conflict = repo_conflicts.get(conn, "cfl_deadbeef")
    assert conflict is not None
    assert conflict.status == ConflictStatus.RESOLVED
    assert conflict.resolution == "Keep both, scoped differently."
    assert conflict.resolved_at == resolved_at


def test_list_all_returns_every_conflict(conn: sqlite3.Connection) -> None:
    repo_conflicts.create(conn, _make_conflict(id="cfl_1", between=["a", "b"]))
    repo_conflicts.create(conn, _make_conflict(id="cfl_2", between=["c", "d"]))
    assert {c.id for c in repo_conflicts.list_all(conn)} == {"cfl_1", "cfl_2"}
