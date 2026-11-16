from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.store import db, repo_rules

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def _make_rule(**overrides: object) -> Rule:
    defaults: dict[str, object] = {
        "id": "ask-follow-up-questions",
        "name": "Ask follow-up questions",
        "imperative": "Ask about what they just said.",
        "rationale": "Follow-ups signal responsiveness.",
        "when_to_apply": "Past the opening two turns.",
        "antipattern": "Changing the subject.",
        "evidence_tier": "A",
        "status": RuleStatus.CANDIDATE,
        "claims": ["clm_1", "clm_2"],
        "rubric": [RubricItem(id="asked_followup", check="Did you ask a follow-up?")],
        "prerequisites": [],
        "created_at": datetime(2026, 9, 22, tzinfo=UTC),
    }
    defaults.update(overrides)
    return Rule(**defaults)  # type: ignore[arg-type]


def test_create_and_get_round_trip(conn: sqlite3.Connection) -> None:
    rule = _make_rule()
    repo_rules.create(conn, rule)
    assert repo_rules.get(conn, rule.id) == rule


def test_get_missing_returns_none(conn: sqlite3.Connection) -> None:
    assert repo_rules.get(conn, "does-not-exist") is None


def test_list_all_orders_by_tier(conn: sqlite3.Connection) -> None:
    repo_rules.create(conn, _make_rule(id="d-rule", evidence_tier="D"))
    repo_rules.create(conn, _make_rule(id="a-rule", evidence_tier="A"))
    repo_rules.create(conn, _make_rule(id="b-rule", evidence_tier="B"))

    assert [r.id for r in repo_rules.list_all(conn)] == ["a-rule", "b-rule", "d-rule"]


def test_find_by_claim_set_matches_regardless_of_order(conn: sqlite3.Connection) -> None:
    rule = _make_rule(claims=["clm_1", "clm_2"])
    repo_rules.create(conn, rule)

    found = repo_rules.find_by_claim_set(conn, {"clm_2", "clm_1"})
    assert found == rule


def test_find_by_claim_set_returns_none_for_a_different_set(conn: sqlite3.Connection) -> None:
    repo_rules.create(conn, _make_rule(claims=["clm_1", "clm_2"]))
    assert repo_rules.find_by_claim_set(conn, {"clm_1"}) is None
    assert repo_rules.find_by_claim_set(conn, {"clm_1", "clm_2", "clm_3"}) is None


def test_set_status_updates_status_and_decided_at(conn: sqlite3.Connection) -> None:
    repo_rules.create(conn, _make_rule())
    decided_at = datetime(2026, 9, 23, tzinfo=UTC)

    repo_rules.set_status(
        conn, "ask-follow-up-questions", RuleStatus.ACCEPTED, decided_at=decided_at
    )

    rule = repo_rules.get(conn, "ask-follow-up-questions")
    assert rule is not None
    assert rule.status == RuleStatus.ACCEPTED
    assert rule.decided_at == decided_at


def test_set_status_can_record_superseded_by(conn: sqlite3.Connection) -> None:
    repo_rules.create(conn, _make_rule(id="old-rule"))
    repo_rules.create(conn, _make_rule(id="new-rule"))

    repo_rules.set_status(
        conn,
        "old-rule",
        RuleStatus.SUPERSEDED,
        decided_at=datetime.now(UTC),
        superseded_by="new-rule",
    )

    rule = repo_rules.get(conn, "old-rule")
    assert rule is not None
    assert rule.superseded_by == "new-rule"


def test_starter_rule_provenance_round_trips(conn: sqlite3.Connection) -> None:
    rule = _make_rule(
        claims=[], basis="Reported across three studies.", cited_sources=["A Paper — Someone, 2017"]
    )
    repo_rules.create(conn, rule)
    assert repo_rules.get(conn, rule.id) == rule
