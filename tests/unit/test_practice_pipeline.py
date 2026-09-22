from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.practice.pipeline import UnknownRuleError, score_drill
from smalltobig.store import db, repo_drills, repo_mastery, repo_rules

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path

    from smalltobig.llm.client import ChatMessage

NOW = datetime(2026, 9, 22, tzinfo=UTC)


class _FakeClient:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def health(self) -> bool:
        return True

    def chat(
        self, messages: list[ChatMessage], *, max_tokens: int = 256, temperature: float = 0.0
    ) -> str:
        return self._reply


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


@pytest.fixture
def rule_id(conn: sqlite3.Connection) -> str:
    rule = Rule(
        id="ask-follow-up-questions",
        name="Ask follow-up questions",
        imperative="Ask about what they just said.",
        rationale="r",
        when_to_apply="w",
        antipattern="a",
        evidence_tier="A",
        status=RuleStatus.ACCEPTED,
        claims=["clm_1"],
        rubric=[RubricItem(id="asked_followup", check="Did you ask a follow-up?")],
        created_at=NOW,
    )
    repo_rules.create(conn, rule)
    return rule.id


def test_score_drill_raises_for_unknown_rule(conn: sqlite3.Connection) -> None:
    with pytest.raises(UnknownRuleError):
        score_drill(conn, _FakeClient("[]"), "does-not-exist", "stimulus", "response")


def test_successful_drill_persists_and_promotes_mastery(
    conn: sqlite3.Connection, rule_id: str
) -> None:
    reply = '[{"rubric_id": "asked_followup", "passed": true, "quote": "great trip"}]'
    drill = score_drill(conn, _FakeClient(reply), rule_id, "stimulus", "Sounds like a great trip!")

    assert drill.success is True
    assert repo_drills.get(conn, drill.id) == drill

    mastery = repo_mastery.get(conn, rule_id)
    assert mastery is not None
    assert mastery.box == 2
    assert mastery.score == 0.5


def test_failed_drill_resets_box_to_one(conn: sqlite3.Connection, rule_id: str) -> None:
    reply = '[{"rubric_id": "asked_followup", "passed": false, "quote": ""}]'
    drill = score_drill(conn, _FakeClient(reply), rule_id, "stimulus", "Nice.")

    assert drill.success is False
    mastery = repo_mastery.get(conn, rule_id)
    assert mastery is not None
    assert mastery.box == 1
    assert mastery.score == 0.0


def test_repeated_drill_successes_never_reach_the_top_box(
    conn: sqlite3.Connection, rule_id: str
) -> None:
    reply = '[{"rubric_id": "asked_followup", "passed": true, "quote": "ok"}]'
    for i in range(10):
        score_drill(conn, _FakeClient(reply), rule_id, "stimulus", f"ok that's great #{i}")

    mastery = repo_mastery.get(conn, rule_id)
    assert mastery is not None
    assert mastery.box == 4
    assert mastery.has_non_drill_evidence is False
