from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.synth.conflicts import find_conflict_candidates, judge_conflict

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


def _rule(rule_id: str, imperative: str) -> Rule:
    return Rule(
        id=rule_id,
        name=rule_id,
        imperative=imperative,
        rationale="r",
        when_to_apply="w",
        antipattern="a",
        evidence_tier="C",
        status=RuleStatus.CANDIDATE,
        claims=["clm_1"],
        rubric=[RubricItem(id="x", check="Did X happen?")],
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
    )


def test_judge_conflict_parses_a_true_verdict() -> None:
    reply = '{"conflict": true, "note": "They contradict.", "proposed_resolution": "Scope both."}'
    result = judge_conflict(_FakeClient(reply), _rule("a", "Do X"), _rule("b", "Never do X"))
    assert result is not None
    assert result.conflict is True
    assert result.note == "They contradict."


def test_judge_conflict_parses_a_false_verdict() -> None:
    reply = '{"conflict": false, "note": "", "proposed_resolution": ""}'
    result = judge_conflict(_FakeClient(reply), _rule("a", "Do X"), _rule("b", "Do Y"))
    assert result is not None
    assert result.conflict is False


def test_judge_conflict_returns_none_for_invalid_json() -> None:
    result = judge_conflict(_FakeClient("not json"), _rule("a", "Do X"), _rule("b", "Do Y"))
    assert result is None


def test_find_conflict_candidates_keeps_only_the_middle_similarity_band() -> None:
    rules = [_rule("a", "x"), _rule("b", "y"), _rule("c", "z"), _rule("d", "w")]
    embeddings = {
        "a": [1.0, 0.0],
        "b": [0.7, 0.3],  # related-but-different from a: mid similarity
        "c": [1.0, 0.0],  # near-identical to a: high similarity, excluded
        "d": [0.0, 1.0],  # unrelated to a: low similarity, excluded
    }
    candidates = find_conflict_candidates(rules[:1] + rules[1:], embeddings, low=0.5, high=0.99)
    pairs = {frozenset((r1.id, r2.id)) for r1, r2 in candidates}
    assert frozenset({"a", "b"}) in pairs
    assert frozenset({"a", "c"}) not in pairs
    assert frozenset({"a", "d"}) not in pairs
