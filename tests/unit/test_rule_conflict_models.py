from __future__ import annotations

from smalltobig.models.conflict import generate_conflict_id
from smalltobig.models.rule import generate_rule_id


def test_generate_rule_id_slugifies_the_name() -> None:
    assert generate_rule_id("Ask follow-up questions") == "ask-follow-up-questions"


def test_generate_rule_id_caps_at_six_words() -> None:
    name = "one two three four five six seven eight"
    assert generate_rule_id(name) == "one-two-three-four-five-six"


def test_generate_conflict_id_is_order_independent() -> None:
    assert generate_conflict_id("rule-a", "rule-b") == generate_conflict_id("rule-b", "rule-a")


def test_generate_conflict_id_differs_for_different_pairs() -> None:
    assert generate_conflict_id("rule-a", "rule-b") != generate_conflict_id("rule-a", "rule-c")
