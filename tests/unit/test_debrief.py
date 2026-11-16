from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.practice.debrief import extract_field_notes, generate_prep_card

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


def _rule(rule_id: str) -> Rule:
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
        rubric=[RubricItem(id="x", check="Did X?")],
        created_at=NOW,
    )


ACCOUNT = "I asked her what the best part of her trip was, and she lit up talking about it."


def test_generate_prep_card_parses_a_clean_reply() -> None:
    reply = (
        '{"topics": ["their recent trip", "weekend plans"], '
        '"exit_line": "I should let you go, great talking to you!"}'
    )
    card = generate_prep_card(_FakeClient(reply), "a work mixer")
    assert card is not None
    assert card.topics == ["their recent trip", "weekend plans"]
    assert "let you go" in card.exit_line


def test_generate_prep_card_returns_none_on_invalid_json() -> None:
    assert generate_prep_card(_FakeClient("not json"), "a party") is None


def test_extract_field_notes_accepts_a_verified_quote() -> None:
    reply = (
        '[{"rule": 1, "addressed": true, "success": true, '
        '"quote": "I asked her what the best part of her trip was"}]'
    )
    notes = extract_field_notes(_FakeClient(reply), ACCOUNT, [_rule("ask-follow-up-questions")])
    assert len(notes) == 1
    assert notes[0].rule_id == "ask-follow-up-questions"
    assert notes[0].success is True


def test_extract_field_notes_drops_a_fabricated_quote() -> None:
    reply = (
        '[{"rule": 1, "addressed": true, "success": true, '
        '"quote": "something never actually said"}]'
    )
    notes = extract_field_notes(_FakeClient(reply), ACCOUNT, [_rule("rule-a")])
    assert notes == []


def test_extract_field_notes_drops_an_unaddressed_rule() -> None:
    reply = '[{"rule": 1, "addressed": false, "success": false, "quote": ""}]'
    notes = extract_field_notes(_FakeClient(reply), ACCOUNT, [_rule("rule-a")])
    assert notes == []


def test_extract_field_notes_drops_an_out_of_range_rule_number() -> None:
    reply = (
        '[{"rule": 5, "addressed": true, "success": true, '
        '"quote": "she lit up talking about it"}]'
    )
    notes = extract_field_notes(_FakeClient(reply), ACCOUNT, [_rule("rule-a")])
    assert notes == []


def test_extract_field_notes_maps_rule_number_to_the_right_rule() -> None:
    reply = (
        '[{"rule": 2, "addressed": true, "success": false, '
        '"quote": "she lit up talking about it"}]'
    )
    notes = extract_field_notes(
        _FakeClient(reply), ACCOUNT, [_rule("rule-a"), _rule("rule-b")]
    )
    assert len(notes) == 1
    assert notes[0].rule_id == "rule-b"
    assert notes[0].success is False


def test_extract_field_notes_empty_rule_list_returns_empty_without_calling_the_model() -> None:
    class _ExplodingClient:
        def health(self) -> bool:
            return True

        def chat(self, *args: object, **kwargs: object) -> str:
            raise AssertionError("should not be called with no rules")

    assert extract_field_notes(_ExplodingClient(), ACCOUNT, []) == []


def test_extract_field_notes_flattens_nested_arrays() -> None:
    reply = (
        '[[{"rule": 1, "addressed": true, "success": true, '
        '"quote": "she lit up talking about it"}]]'
    )
    notes = extract_field_notes(_FakeClient(reply), ACCOUNT, [_rule("rule-a")])
    assert len(notes) == 1


def test_extract_field_notes_handles_invalid_json() -> None:
    assert extract_field_notes(_FakeClient("not json"), ACCOUNT, [_rule("rule-a")]) == []


def test_extract_field_notes_no_rule_addressed_returns_empty() -> None:
    assert extract_field_notes(_FakeClient("[]"), ACCOUNT, [_rule("rule-a")]) == []
