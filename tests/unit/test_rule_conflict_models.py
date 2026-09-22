from __future__ import annotations

from datetime import UTC, datetime

from smalltobig.models.conflict import generate_conflict_id
from smalltobig.models.lesson import generate_lesson_id
from smalltobig.models.rule import generate_rule_id
from smalltobig.models.session import generate_session_id


def test_generate_rule_id_slugifies_the_name() -> None:
    assert generate_rule_id("Ask follow-up questions") == "ask-follow-up-questions"


def test_generate_rule_id_caps_at_six_words() -> None:
    name = "one two three four five six seven eight"
    assert generate_rule_id(name) == "one-two-three-four-five-six"


def test_generate_conflict_id_is_order_independent() -> None:
    assert generate_conflict_id("rule-a", "rule-b") == generate_conflict_id("rule-b", "rule-a")


def test_generate_conflict_id_differs_for_different_pairs() -> None:
    assert generate_conflict_id("rule-a", "rule-b") != generate_conflict_id("rule-a", "rule-c")


def test_generate_lesson_id_slugifies_the_name() -> None:
    assert generate_lesson_id("Ask and Listen") == "ask-and-listen"


def test_generate_session_id_is_deterministic_for_the_same_inputs() -> None:
    now = datetime(2026, 9, 22, tzinfo=UTC)
    assert generate_session_id("lesson-a", "elevator", now) == generate_session_id(
        "lesson-a", "elevator", now
    )


def test_generate_session_id_differs_for_different_timestamps() -> None:
    now = datetime(2026, 9, 22, tzinfo=UTC)
    later = datetime(2026, 9, 23, tzinfo=UTC)
    assert generate_session_id("lesson-a", "elevator", now) != generate_session_id(
        "lesson-a", "elevator", later
    )
