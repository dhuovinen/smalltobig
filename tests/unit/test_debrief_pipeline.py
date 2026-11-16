from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.practice.pipeline import submit_debrief
from smalltobig.store import db, repo_debriefs, repo_field_notes, repo_mastery, repo_rules

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path

    from smalltobig.llm.client import ChatMessage

NOW = datetime(2026, 9, 22, tzinfo=UTC)

ACCOUNT = "I asked her what the best part of her trip was, and she lit up talking about it."


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


def test_no_accepted_rules_persists_debrief_with_no_field_notes(
    conn: sqlite3.Connection,
) -> None:
    debrief, notes = submit_debrief(conn, _FakeClient("[]"), ACCOUNT)
    assert notes == []
    assert repo_debriefs.get(conn, debrief.id) == debrief


def test_successful_field_note_persists_and_weights_mastery_at_3x(
    conn: sqlite3.Connection, rule_id: str
) -> None:
    reply = (
        '[{"rule": 1, "addressed": true, "success": true, '
        '"quote": "I asked her what the best part of her trip was"}]'
    )
    debrief, notes = submit_debrief(conn, _FakeClient(reply), ACCOUNT)

    assert len(notes) == 1
    assert repo_field_notes.list_by_debrief(conn, debrief.id) == notes

    mastery = repo_mastery.get(conn, rule_id)
    assert mastery is not None
    assert mastery.box == 2
    assert mastery.score == 3.0  # field-note weight, not drill's 0.5 or roleplay's 1.0
    assert mastery.has_non_drill_evidence is True


def test_a_missed_field_note_resets_box_but_still_unlocks_the_ceiling(
    conn: sqlite3.Connection, rule_id: str
) -> None:
    reply = (
        '[{"rule": 1, "addressed": true, "success": false, '
        '"quote": "I asked her what the best part of her trip was"}]'
    )
    submit_debrief(conn, _FakeClient(reply), ACCOUNT)

    mastery = repo_mastery.get(conn, rule_id)
    assert mastery is not None
    assert mastery.box == 1
    assert mastery.has_non_drill_evidence is True


def test_repeated_field_notes_alone_can_reach_the_top_box_quickly(
    conn: sqlite3.Connection, rule_id: str
) -> None:
    reply = (
        '[{"rule": 1, "addressed": true, "success": true, '
        '"quote": "I asked her what the best part of her trip was"}]'
    )
    for _ in range(4):
        submit_debrief(conn, _FakeClient(reply), ACCOUNT)

    mastery = repo_mastery.get(conn, rule_id)
    assert mastery is not None
    assert mastery.box == 5
