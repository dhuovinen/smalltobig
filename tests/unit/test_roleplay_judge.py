from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.models.session import Turn
from smalltobig.practice.judge import judge_session

if TYPE_CHECKING:
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


def _rule(rule_id: str, rubric_id: str = "x") -> Rule:
    return Rule(
        id=rule_id,
        name=rule_id,
        imperative=f"{rule_id}.",
        rationale="r",
        when_to_apply="w",
        antipattern="a",
        evidence_tier="A",
        status=RuleStatus.ACCEPTED,
        claims=["clm_1"],
        rubric=[RubricItem(id=rubric_id, check="Did X?")],
        created_at=NOW,
    )


TURNS = [
    Turn(speaker="partner", text="Busy day?"),
    Turn(speaker="user", text="Yeah! What about you, anything exciting?"),
]


def test_judge_session_accepts_a_verified_quote() -> None:
    reply = '[{"item": 1, "passed": true, "quote": "What about you, anything exciting?"}]'
    results = judge_session(_FakeClient(reply), TURNS, [_rule("rule-a")])
    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].quote == "What about you, anything exciting?"


def test_judge_session_downgrades_a_fabricated_quote() -> None:
    reply = '[{"item": 1, "passed": true, "quote": "not in transcript"}]'
    results = judge_session(_FakeClient(reply), TURNS, [_rule("rule-a")])
    assert results[0].passed is False
    assert results[0].quote is None


def test_judge_session_a_quote_from_the_partners_turn_is_rejected() -> None:
    # Rubric spans must come from the practicer's OWN turns, not the
    # roleplay partner's — a quote that's only in a "partner" turn must
    # not verify against user_text.
    reply = '[{"item": 1, "passed": true, "quote": "Busy day?"}]'
    results = judge_session(_FakeClient(reply), TURNS, [_rule("rule-a")])
    assert results[0].passed is False


def test_judge_session_handles_multiple_rules() -> None:
    reply = (
        '[{"item": 1, "passed": true, "quote": "Yeah!"}, '
        '{"item": 2, "passed": false, "quote": ""}]'
    )
    results = judge_session(
        _FakeClient(reply), TURNS, [_rule("rule-a", "x"), _rule("rule-b", "y")]
    )
    by_key = {(r.rule_id, r.rubric_id): r for r in results}
    assert by_key[("rule-a", "x")].passed is True
    assert by_key[("rule-b", "y")].passed is False


def test_judge_session_flattens_nested_arrays() -> None:
    reply = '[[{"item": 1, "passed": true, "quote": "Yeah!"}]]'
    results = judge_session(_FakeClient(reply), TURNS, [_rule("rule-a")])
    assert results[0].passed is True


def test_judge_session_defaults_missing_items_to_failed() -> None:
    results = judge_session(_FakeClient("[]"), TURNS, [_rule("rule-a")])
    assert len(results) == 1
    assert results[0].passed is False


def test_judge_session_handles_invalid_json() -> None:
    results = judge_session(_FakeClient("not json"), TURNS, [_rule("rule-a")])
    assert len(results) == 1
    assert results[0].passed is False


def test_judge_session_ignores_a_garbled_id_as_long_as_position_matches() -> None:
    # Observed live: with a single rule/rubric item, a 3B model sometimes
    # blends rule_id and rubric_id into one garbled token instead of
    # copying either exactly — even while supplying a genuinely valid
    # quote. Position-based matching must not depend on any id string.
    reply = '[{"item": 1, "passed": true, "quote": "What about you, anything exciting?"}]'
    rule = _rule("ask-follow-up-questions", "asked_followup")
    results = judge_session(_FakeClient(reply), TURNS, [rule])
    assert results[0].passed is True
    assert results[0].rule_id == "ask-follow-up-questions"
    assert results[0].rubric_id == "asked_followup"
