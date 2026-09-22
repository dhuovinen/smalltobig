from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from smalltobig.models.session import Session, SessionRubricResult, Turn
from smalltobig.store import db, repo_sessions

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


def _session(**overrides: object) -> Session:
    defaults: dict[str, object] = {
        "id": "ses_deadbeef",
        "lesson_id": "some-lesson",
        "scenario_id": "elevator",
        "rule_ids": ["ask-follow-up-questions"],
        "turns": [
            Turn(speaker="partner", text="Busy day?"),
            Turn(speaker="user", text="Yeah, what about you?"),
        ],
        "rubric_results": [
            SessionRubricResult(
                rule_id="ask-follow-up-questions",
                rubric_id="asked_followup",
                passed=True,
                quote="what about you?",
            )
        ],
        "created_at": NOW,
        "ended_at": NOW,
    }
    defaults.update(overrides)
    return Session(**defaults)  # type: ignore[arg-type]


def test_create_and_get_round_trip(conn: sqlite3.Connection) -> None:
    session = _session()
    repo_sessions.create(conn, session)
    assert repo_sessions.get(conn, session.id) == session


def test_get_missing_returns_none(conn: sqlite3.Connection) -> None:
    assert repo_sessions.get(conn, "does-not-exist") is None


def test_list_by_lesson_orders_most_recent_first(conn: sqlite3.Connection) -> None:
    older = _session(id="ses_1", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = _session(id="ses_2", created_at=datetime(2026, 6, 1, tzinfo=UTC))
    repo_sessions.create(conn, older)
    repo_sessions.create(conn, newer)

    ids = [s.id for s in repo_sessions.list_by_lesson(conn, "some-lesson")]
    assert ids == ["ses_2", "ses_1"]


def test_list_by_lesson_only_returns_that_lesson(conn: sqlite3.Connection) -> None:
    repo_sessions.create(conn, _session(id="ses_a", lesson_id="lesson-a"))
    repo_sessions.create(conn, _session(id="ses_b", lesson_id="lesson-b"))

    assert [s.id for s in repo_sessions.list_by_lesson(conn, "lesson-a")] == ["ses_a"]


def test_list_all_returns_every_session(conn: sqlite3.Connection) -> None:
    repo_sessions.create(conn, _session(id="ses_a", lesson_id="lesson-a"))
    repo_sessions.create(conn, _session(id="ses_b", lesson_id="lesson-b"))
    assert {s.id for s in repo_sessions.list_all(conn)} == {"ses_a", "ses_b"}


def test_multi_rule_session_round_trips_all_rubric_results(conn: sqlite3.Connection) -> None:
    session = _session(
        rule_ids=["rule-a", "rule-b"],
        rubric_results=[
            SessionRubricResult(rule_id="rule-a", rubric_id="x", passed=True, quote="ok"),
            SessionRubricResult(rule_id="rule-b", rubric_id="y", passed=False, quote=None),
        ],
    )
    repo_sessions.create(conn, session)
    fetched = repo_sessions.get(conn, session.id)
    assert fetched is not None
    assert len(fetched.rubric_results) == 2
    assert {r.rule_id for r in fetched.rubric_results} == {"rule-a", "rule-b"}
