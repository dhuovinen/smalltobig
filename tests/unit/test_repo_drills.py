from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from smalltobig.models.drill import Drill, RubricResult
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.store import db, repo_drills, repo_rules

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
            status=RuleStatus.CANDIDATE,
            claims=["clm_1"],
            rubric=[RubricItem(id="x", check="Did X?")],
            created_at=NOW,
        ),
    )


def _drill(**overrides: object) -> Drill:
    defaults: dict[str, object] = {
        "id": "drl_deadbeef",
        "rule_id": "some-rule",
        "stimulus": "They say: I just got back from Japan.",
        "response": "What was the best part of the trip?",
        "rubric_results": [
            RubricResult(rubric_id="x", passed=True, quote="What was the best part")
        ],
        "success": True,
        "created_at": NOW,
    }
    defaults.update(overrides)
    return Drill(**defaults)  # type: ignore[arg-type]


def test_create_and_get_round_trip(conn: sqlite3.Connection) -> None:
    _ensure_rule(conn, "some-rule")
    drill = _drill()
    repo_drills.create(conn, drill)
    assert repo_drills.get(conn, drill.id) == drill


def test_get_missing_returns_none(conn: sqlite3.Connection) -> None:
    assert repo_drills.get(conn, "does-not-exist") is None


def test_list_by_rule_orders_most_recent_first(conn: sqlite3.Connection) -> None:
    _ensure_rule(conn, "some-rule")
    older = _drill(id="drl_1", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = _drill(id="drl_2", created_at=datetime(2026, 6, 1, tzinfo=UTC))
    repo_drills.create(conn, older)
    repo_drills.create(conn, newer)

    assert [d.id for d in repo_drills.list_by_rule(conn, "some-rule")] == ["drl_2", "drl_1"]


def test_list_by_rule_only_returns_that_rule(conn: sqlite3.Connection) -> None:
    _ensure_rule(conn, "rule-a")
    _ensure_rule(conn, "rule-b")
    repo_drills.create(conn, _drill(id="drl_a", rule_id="rule-a"))
    repo_drills.create(conn, _drill(id="drl_b", rule_id="rule-b"))

    assert [d.id for d in repo_drills.list_by_rule(conn, "rule-a")] == ["drl_a"]


def test_failed_drill_round_trips_without_a_quote(conn: sqlite3.Connection) -> None:
    _ensure_rule(conn, "some-rule")
    drill = _drill(
        rubric_results=[RubricResult(rubric_id="x", passed=False, quote=None)], success=False
    )
    repo_drills.create(conn, drill)
    fetched = repo_drills.get(conn, drill.id)
    assert fetched is not None
    assert fetched.success is False
    assert fetched.rubric_results[0].quote is None
