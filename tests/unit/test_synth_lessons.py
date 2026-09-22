from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from smalltobig.models.mastery import Mastery
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.synth.lessons import name_lesson, order_rules_for_lessons

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


def _rule(rule_id: str, *, tier: str = "C", prerequisites: list[str] | None = None) -> Rule:
    return Rule(
        id=rule_id,
        name=rule_id,
        imperative=f"{rule_id}.",
        rationale="r",
        when_to_apply="w",
        antipattern="a",
        evidence_tier=tier,  # type: ignore[arg-type]
        status=RuleStatus.ACCEPTED,
        claims=["clm_1"],
        rubric=[RubricItem(id="x", check="Did X?")],
        prerequisites=prerequisites or [],
        created_at=NOW,
    )


def test_orders_by_evidence_tier_first() -> None:
    rules = [_rule("d-rule", tier="D"), _rule("a-rule", tier="A"), _rule("b-rule", tier="B")]
    ordered = order_rules_for_lessons(rules, {})
    assert [r.id for r in ordered] == ["a-rule", "b-rule", "d-rule"]


def test_orders_by_weakest_mastery_within_the_same_tier() -> None:
    rules = [_rule("strong", tier="B"), _rule("weak", tier="B")]
    mastery = {
        "strong": Mastery(rule_id="strong", score=5.0, updated_at=NOW),
        "weak": Mastery(rule_id="weak", score=0.5, updated_at=NOW),
    }
    ordered = order_rules_for_lessons(rules, mastery)
    assert [r.id for r in ordered] == ["weak", "strong"]


def test_a_prerequisite_is_sequenced_before_its_dependent() -> None:
    # dependent is tier A (would otherwise sort first); its prerequisite
    # is tier D (would otherwise sort last) — the DAG must win.
    dependent = _rule("dependent", tier="A", prerequisites=["prereq"])
    prereq = _rule("prereq", tier="D")
    ordered = order_rules_for_lessons([dependent, prereq], {})
    assert [r.id for r in ordered] == ["prereq", "dependent"]


def test_a_prerequisite_not_in_the_accepted_set_is_skipped_not_an_error() -> None:
    rule = _rule("solo", prerequisites=["never-accepted"])
    ordered = order_rules_for_lessons([rule], {})
    assert [r.id for r in ordered] == ["solo"]


def test_name_lesson_uses_the_model_reply() -> None:
    reply = '{"name": "Ask and Listen"}'
    name = name_lesson(_FakeClient(reply), [_rule("a"), _rule("b")])
    assert name == "Ask and Listen"


def test_name_lesson_falls_back_to_joined_rule_names_on_bad_json() -> None:
    name = name_lesson(_FakeClient("not json"), [_rule("rule-a"), _rule("rule-b")])
    assert name == "rule-a / rule-b"


def test_name_lesson_falls_back_on_an_empty_name() -> None:
    name = name_lesson(_FakeClient('{"name": ""}'), [_rule("rule-a")])
    assert name == "rule-a"
