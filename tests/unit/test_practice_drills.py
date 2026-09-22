from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.practice.drills import generate_stimulus, judge_drill_response

if TYPE_CHECKING:
    from smalltobig.llm.client import ChatMessage


class _FakeClient:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def health(self) -> bool:
        return True

    def chat(
        self, messages: list[ChatMessage], *, max_tokens: int = 256, temperature: float = 0.0
    ) -> str:
        return self._reply


def _rule(**overrides: object) -> Rule:
    defaults: dict[str, object] = {
        "id": "ask-follow-up-questions",
        "name": "Ask follow-up questions",
        "imperative": "Ask about what they just said.",
        "rationale": "r",
        "when_to_apply": "w",
        "antipattern": "a",
        "evidence_tier": "A",
        "status": RuleStatus.ACCEPTED,
        "claims": ["clm_1"],
        "rubric": [
            RubricItem(id="asked_followup", check="Did you ask a follow-up?"),
            RubricItem(id="no_topic_jump", check="Did you avoid a new topic?"),
        ],
        "created_at": datetime(2026, 9, 22, tzinfo=UTC),
    }
    defaults.update(overrides)
    return Rule(**defaults)  # type: ignore[arg-type]


def test_generate_stimulus_strips_wrapping_quotes() -> None:
    stimulus = generate_stimulus(_FakeClient('"I just got back from Japan."'), _rule())
    assert stimulus == "I just got back from Japan."


def test_judge_drill_response_accepts_a_verified_quote() -> None:
    response = "That sounds amazing, what was the best part of the trip?"
    reply = (
        '[{"rubric_id": "asked_followup", "passed": true, '
        '"quote": "what was the best part of the trip?"}, '
        '{"rubric_id": "no_topic_jump", "passed": true, "quote": "That sounds amazing"}]'
    )
    results = judge_drill_response(_FakeClient(reply), _rule(), "stimulus", response)
    assert all(result.passed for result in results)
    assert results[0].quote == "what was the best part of the trip?"


def test_judge_drill_response_downgrades_a_passed_claim_with_a_fabricated_quote() -> None:
    # The model says "passed" but the quote it offers isn't actually in
    # the response — this is exactly what the verify gate exists to catch.
    response = "Cool, anyway I went skiing last winter."
    reply = (
        '[{"rubric_id": "asked_followup", "passed": true, '
        '"quote": "what was the best part of the trip?"}, '
        '{"rubric_id": "no_topic_jump", "passed": false, "quote": ""}]'
    )
    results = judge_drill_response(_FakeClient(reply), _rule(), "stimulus", response)
    assert results[0].passed is False
    assert results[0].quote is None


def test_judge_drill_response_defaults_missing_items_to_failed() -> None:
    reply = '[{"rubric_id": "asked_followup", "passed": true, "quote": "hi"}]'
    results = judge_drill_response(_FakeClient(reply), _rule(), "stimulus", "hi there")
    assert len(results) == 2
    by_id = {result.rubric_id: result for result in results}
    assert by_id["no_topic_jump"].passed is False


def test_judge_drill_response_flattens_items_the_model_wrapped_individually() -> None:
    # Observed live with a 3B model: instead of one flat array, it
    # returned one single-element array per rubric item.
    response = "That sounds great, what trails have you been on?"
    reply = (
        '[[{"rubric_id": "asked_followup", "passed": true, '
        '"quote": "what trails have you been on?"}], '
        '[{"rubric_id": "no_topic_jump", "passed": true, "quote": "That sounds great"}]]'
    )
    results = judge_drill_response(_FakeClient(reply), _rule(), "stimulus", response)
    assert all(result.passed for result in results)
    assert results[0].quote == "what trails have you been on?"


def test_judge_drill_response_handles_invalid_json() -> None:
    results = judge_drill_response(_FakeClient("not json"), _rule(), "stimulus", "some response")
    assert len(results) == 2
    assert all(not result.passed for result in results)
