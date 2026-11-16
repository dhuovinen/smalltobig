from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from smalltobig.models.field_note import Debrief, FieldNote
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.store import db, repo_debriefs, repo_field_notes, repo_rules

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


def _ensure_rule(conn: sqlite3.Connection, rule_id: str) -> None:
    repo_rules.create(
        conn,
        Rule(
            id=rule_id,
            name=rule_id,
            imperative="i",
            rationale="r",
            when_to_apply="w",
            antipattern="a",
            evidence_tier="C",
            status=RuleStatus.ACCEPTED,
            claims=["clm_1"],
            rubric=[RubricItem(id="x", check="Did X?")],
            created_at=NOW,
        ),
    )


def _ensure_debrief(conn: sqlite3.Connection, debrief_id: str) -> None:
    repo_debriefs.create(conn, Debrief(id=debrief_id, text="Some account.", created_at=NOW))


def _field_note(**overrides: object) -> FieldNote:
    defaults: dict[str, object] = {
        "id": "fn_1",
        "debrief_id": "dbf_1",
        "rule_id": "some-rule",
        "quote": "asked a great question",
        "success": True,
        "created_at": NOW,
    }
    defaults.update(overrides)
    return FieldNote(**defaults)  # type: ignore[arg-type]


def test_create_and_list_by_rule_round_trip(conn: sqlite3.Connection) -> None:
    _ensure_rule(conn, "some-rule")
    _ensure_debrief(conn, "dbf_1")
    note = _field_note()
    repo_field_notes.create(conn, note)

    assert repo_field_notes.list_by_rule(conn, "some-rule") == [note]


def test_list_by_rule_only_returns_that_rule(conn: sqlite3.Connection) -> None:
    _ensure_rule(conn, "rule-a")
    _ensure_rule(conn, "rule-b")
    _ensure_debrief(conn, "dbf_1")
    repo_field_notes.create(conn, _field_note(id="fn_a", rule_id="rule-a"))
    repo_field_notes.create(conn, _field_note(id="fn_b", rule_id="rule-b"))

    assert [n.id for n in repo_field_notes.list_by_rule(conn, "rule-a")] == ["fn_a"]


def test_list_by_debrief_returns_every_note_from_that_debrief(conn: sqlite3.Connection) -> None:
    _ensure_rule(conn, "rule-a")
    _ensure_rule(conn, "rule-b")
    _ensure_debrief(conn, "dbf_1")
    repo_field_notes.create(conn, _field_note(id="fn_a", rule_id="rule-a", debrief_id="dbf_1"))
    repo_field_notes.create(conn, _field_note(id="fn_b", rule_id="rule-b", debrief_id="dbf_1"))

    assert {n.id for n in repo_field_notes.list_by_debrief(conn, "dbf_1")} == {"fn_a", "fn_b"}


def test_list_all_returns_every_note(conn: sqlite3.Connection) -> None:
    _ensure_rule(conn, "some-rule")
    _ensure_debrief(conn, "dbf_1")
    repo_field_notes.create(conn, _field_note())
    assert len(repo_field_notes.list_all(conn)) == 1


def test_a_missed_note_round_trips_success_false(conn: sqlite3.Connection) -> None:
    _ensure_rule(conn, "some-rule")
    _ensure_debrief(conn, "dbf_1")
    note = _field_note(success=False)
    repo_field_notes.create(conn, note)

    fetched = repo_field_notes.list_by_rule(conn, "some-rule")[0]
    assert fetched.success is False
