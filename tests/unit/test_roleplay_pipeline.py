from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from smalltobig.config import Settings
from smalltobig.models.lesson import Lesson
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.models.session import Turn
from smalltobig.practice.pipeline import UnknownLessonError, end_roleplay_session
from smalltobig.store import db, repo_lessons, repo_mastery, repo_rules, repo_sessions

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path

    from smalltobig.llm.client import ChatMessage

NOW = datetime(2026, 9, 22, tzinfo=UTC)

TURNS = [
    Turn(speaker="partner", text="Busy day?"),
    Turn(speaker="user", text="Yeah! What about you, anything exciting?"),
]


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
def settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None, data_dir=tmp_path / "data", repo_root=tmp_path / "repo"
    )


@pytest.fixture
def conn(settings: Settings) -> Iterator[sqlite3.Connection]:
    connection = db.connect(settings.db_path)
    yield connection
    connection.close()


@pytest.fixture
def lesson_id(conn: sqlite3.Connection, settings: Settings) -> str:
    repo_rules.create(
        conn,
        Rule(
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
        ),
    )
    lesson = Lesson(
        id="ask-and-listen",
        name="Ask and Listen",
        rule_ids=["ask-follow-up-questions"],
        created_at=NOW,
    )
    repo_lessons.create(settings, lesson)
    return lesson.id


def test_raises_for_unknown_lesson(conn: sqlite3.Connection, settings: Settings) -> None:
    with pytest.raises(UnknownLessonError):
        end_roleplay_session(
            conn, settings, _FakeClient("[]"), "does-not-exist", "elevator", TURNS
        )


def test_successful_session_persists_and_promotes_mastery(
    conn: sqlite3.Connection, settings: Settings, lesson_id: str
) -> None:
    reply = '[{"item": 1, "passed": true, "quote": "What about you, anything exciting?"}]'
    session = end_roleplay_session(
        conn, settings, _FakeClient(reply), lesson_id, "elevator", TURNS
    )

    assert session.rule_ids == ["ask-follow-up-questions"]
    assert repo_sessions.get(conn, session.id) == session

    mastery = repo_mastery.get(conn, "ask-follow-up-questions")
    assert mastery is not None
    assert mastery.box == 2
    assert mastery.score == 1.0  # roleplay weight
    assert mastery.has_non_drill_evidence is True


def test_a_failed_session_still_unlocks_the_box_five_ceiling(
    conn: sqlite3.Connection, settings: Settings, lesson_id: str
) -> None:
    end_roleplay_session(conn, settings, _FakeClient("[]"), lesson_id, "elevator", TURNS)

    mastery = repo_mastery.get(conn, "ask-follow-up-questions")
    assert mastery is not None
    assert mastery.box == 1
    assert mastery.has_non_drill_evidence is True


def test_after_a_roleplay_signal_drill_successes_can_reach_the_top_box(
    conn: sqlite3.Connection, settings: Settings, lesson_id: str
) -> None:
    from smalltobig.models.mastery import SignalType
    from smalltobig.progress.leitner import apply_signal

    reply = '[{"item": 1, "passed": true, "quote": "What about you, anything exciting?"}]'
    end_roleplay_session(conn, settings, _FakeClient(reply), lesson_id, "elevator", TURNS)

    mastery = repo_mastery.get(conn, "ask-follow-up-questions")
    assert mastery is not None
    for _ in range(5):
        mastery = apply_signal(mastery, SignalType.DRILL, success=True, now=NOW)
    assert mastery.box == 5


def test_multi_rule_lesson_updates_mastery_independently_per_rule(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    repo_rules.create(
        conn,
        Rule(
            id="rule-b",
            name="rule-b",
            imperative="i",
            rationale="r",
            when_to_apply="w",
            antipattern="a",
            evidence_tier="C",
            status=RuleStatus.ACCEPTED,
            claims=["clm_2"],
            rubric=[RubricItem(id="y", check="Did Y?")],
            created_at=NOW,
        ),
    )
    repo_rules.create(
        conn,
        Rule(
            id="rule-a",
            name="rule-a",
            imperative="i",
            rationale="r",
            when_to_apply="w",
            antipattern="a",
            evidence_tier="C",
            status=RuleStatus.ACCEPTED,
            claims=["clm_1"],
            rubric=[RubricItem(id="x", check="Did X?")],
            created_at=NOW,
        ),
    )
    lesson = Lesson(
        id="two-rule-lesson", name="Two Rules", rule_ids=["rule-a", "rule-b"], created_at=NOW
    )
    repo_lessons.create(settings, lesson)

    reply = (
        '[{"item": 1, "passed": true, "quote": "Yeah!"}, '
        '{"item": 2, "passed": false, "quote": ""}]'
    )
    end_roleplay_session(conn, settings, _FakeClient(reply), lesson.id, "elevator", TURNS)

    mastery_a = repo_mastery.get(conn, "rule-a")
    mastery_b = repo_mastery.get(conn, "rule-b")
    assert mastery_a is not None
    assert mastery_b is not None
    assert mastery_a.box == 2
    assert mastery_b.box == 1
