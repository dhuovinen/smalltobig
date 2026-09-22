from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from smalltobig.models.claim import Claim, ClaimStatus, ClaimType
from smalltobig.models.source import Source, SourceKind
from smalltobig.store import db, repo_claims, repo_sources

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def _ensure_source(conn: sqlite3.Connection, source_id: str) -> None:
    """Claims carry a foreign key to sources — insert a minimal one so
    round-trip tests aren't testing against a row that can't exist."""
    repo_sources.create(
        conn,
        Source(
            id=source_id,
            title=source_id,
            kind=SourceKind.NOTES,
            retrieved_at=datetime(2026, 9, 22, tzinfo=UTC),
            sha256=source_id.ljust(64, "0"),
        ),
        raw_extension=".txt",
    )


def _make_claim(**overrides: object) -> Claim:
    defaults: dict[str, object] = {
        "id": "clm_deadbeef",
        "source_id": "src_example",
        "chunk_index": 0,
        "verbatim": "Ask follow-up questions.",
        "paraphrase": "Follow up.",
        "claim_type": ClaimType.PRESCRIPTIVE,
        "status": ClaimStatus.ACCEPTED,
        "start": 10,
        "end": 34,
        "rejection_reason": None,
        "created_at": datetime(2026, 9, 22, tzinfo=UTC),
    }
    defaults.update(overrides)
    return Claim(**defaults)  # type: ignore[arg-type]


def test_create_and_list_by_source_round_trip(conn: sqlite3.Connection) -> None:
    _ensure_source(conn, "src_example")
    claim = _make_claim()
    repo_claims.create(conn, claim)

    fetched = repo_claims.list_by_source(conn, "src_example")
    assert fetched == [claim]


def test_list_by_source_only_returns_that_source(conn: sqlite3.Connection) -> None:
    _ensure_source(conn, "src_a")
    _ensure_source(conn, "src_b")
    repo_claims.create(conn, _make_claim(id="clm_1", source_id="src_a"))
    repo_claims.create(conn, _make_claim(id="clm_2", source_id="src_b"))

    assert [c.id for c in repo_claims.list_by_source(conn, "src_a")] == ["clm_1"]


def test_rejected_claim_round_trips_without_a_span(conn: sqlite3.Connection) -> None:
    _ensure_source(conn, "src_example")
    claim = _make_claim(
        id="clm_rejected",
        status=ClaimStatus.REJECTED,
        start=None,
        end=None,
        rejection_reason="span not found in source",
    )
    repo_claims.create(conn, claim)

    fetched = repo_claims.list_by_source(conn, "src_example")
    assert fetched[0].status == ClaimStatus.REJECTED
    assert fetched[0].start is None
    assert fetched[0].rejection_reason == "span not found in source"


def test_delete_by_source_clears_only_that_sources_claims(conn: sqlite3.Connection) -> None:
    _ensure_source(conn, "src_a")
    _ensure_source(conn, "src_b")
    repo_claims.create(conn, _make_claim(id="clm_1", source_id="src_a"))
    repo_claims.create(conn, _make_claim(id="clm_2", source_id="src_b"))

    repo_claims.delete_by_source(conn, "src_a")

    assert repo_claims.list_by_source(conn, "src_a") == []
    assert len(repo_claims.list_by_source(conn, "src_b")) == 1
