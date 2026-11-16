from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from smalltobig.config import Settings
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.store import db, repo_lessons, repo_rules
from smalltobig.synth.pipeline import generate_lessons

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path

    from smalltobig.llm.client import ChatMessage

NOW = datetime(2026, 9, 22, tzinfo=UTC)


class _ScriptedClient:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)

    def health(self) -> bool:
        return True

    def chat(
        self, messages: list[ChatMessage], *, max_tokens: int = 256, temperature: float = 0.0
    ) -> str:
        return self._replies.pop(0)


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


def _accept_rule(conn: sqlite3.Connection, rule_id: str, tier: str = "C") -> None:
    repo_rules.create(
        conn,
        Rule(
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
            created_at=NOW,
        ),
    )


def test_no_accepted_rules_yields_an_empty_summary(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    summary = generate_lessons(conn, settings, _ScriptedClient([]))
    assert summary.accepted_rules == 0
    assert summary.lessons_created == 0


def test_groups_rules_into_lessons_of_up_to_group_size(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    for i in range(5):
        _accept_rule(conn, f"rule-{i}")

    replies = ['{"name": "Lesson One"}', '{"name": "Lesson Two"}']
    summary = generate_lessons(conn, settings, _ScriptedClient(replies), group_size=3)

    assert summary.accepted_rules == 5
    assert summary.lessons_created == 2
    lessons = repo_lessons.list_all(settings)
    assert len(lessons) == 2
    assert sum(len(lesson.rule_ids) for lesson in lessons) == 5


def test_rerunning_only_covers_rules_not_already_in_a_lesson(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    _accept_rule(conn, "rule-a")
    generate_lessons(conn, settings, _ScriptedClient(['{"name": "First"}']), group_size=3)
    assert len(repo_lessons.list_all(settings)) == 1

    _accept_rule(conn, "rule-b")
    summary = generate_lessons(
        conn, settings, _ScriptedClient(['{"name": "Second"}']), group_size=3
    )

    assert summary.already_lessoned == 1
    assert summary.lessons_created == 1
    lessons = repo_lessons.list_all(settings)
    assert len(lessons) == 2
    all_rule_ids = {rid for lesson in lessons for rid in lesson.rule_ids}
    assert all_rule_ids == {"rule-a", "rule-b"}


def test_a_hand_edited_lesson_is_never_touched_by_a_rerun(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    _accept_rule(conn, "rule-a")
    generate_lessons(conn, settings, _ScriptedClient(['{"name": "Original Name"}']), group_size=3)

    lesson = repo_lessons.list_all(settings)[0]
    hand_edited = lesson.model_copy(update={"name": "Hand-Edited Name"})
    repo_lessons.create(settings, hand_edited)

    generate_lessons(conn, settings, _ScriptedClient([]), group_size=3)

    fetched = repo_lessons.get(settings, lesson.id)
    assert fetched is not None
    assert fetched.name == "Hand-Edited Name"
