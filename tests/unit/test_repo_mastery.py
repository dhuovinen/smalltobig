from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from smalltobig.models.mastery import Mastery
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.store import db, repo_mastery, repo_rules

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


def test_get_missing_returns_none(conn: sqlite3.Connection) -> None:
    assert repo_mastery.get(conn, "does-not-exist") is None


def test_get_or_default_returns_a_fresh_record(conn: sqlite3.Connection) -> None:
    mastery = repo_mastery.get_or_default(conn, "some-rule", now=NOW)
    assert mastery.box == 1
    assert mastery.score == 0.0
    assert mastery.has_non_drill_evidence is False
    # Not persisted just by asking for the default.
    assert repo_mastery.get(conn, "some-rule") is None


def test_upsert_then_get_round_trips(conn: sqlite3.Connection) -> None:
    _ensure_rule(conn, "some-rule")
    mastery = Mastery(
        rule_id="some-rule", box=3, score=1.5, has_non_drill_evidence=True, updated_at=NOW
    )
    repo_mastery.upsert(conn, mastery)
    assert repo_mastery.get(conn, "some-rule") == mastery


def test_upsert_overwrites_the_existing_row(conn: sqlite3.Connection) -> None:
    _ensure_rule(conn, "some-rule")
    repo_mastery.upsert(
        conn, Mastery(rule_id="some-rule", box=1, score=0.0, updated_at=NOW)
    )
    updated = Mastery(rule_id="some-rule", box=4, score=2.0, updated_at=NOW)
    repo_mastery.upsert(conn, updated)

    assert repo_mastery.get(conn, "some-rule") == updated


def test_list_all_orders_weakest_score_first(conn: sqlite3.Connection) -> None:
    _ensure_rule(conn, "rule-a")
    _ensure_rule(conn, "rule-b")
    repo_mastery.upsert(conn, Mastery(rule_id="rule-a", score=5.0, updated_at=NOW))
    repo_mastery.upsert(conn, Mastery(rule_id="rule-b", score=1.0, updated_at=NOW))

    assert [m.rule_id for m in repo_mastery.list_all(conn)] == ["rule-b", "rule-a"]
