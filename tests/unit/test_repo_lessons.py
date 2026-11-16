from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from smalltobig.config import Settings
from smalltobig.models.lesson import Lesson
from smalltobig.store import repo_lessons

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, repo_root=tmp_path / "repo")  # type: ignore[call-arg]


def _lesson(**overrides: object) -> Lesson:
    from datetime import UTC, datetime

    defaults: dict[str, object] = {
        "id": "ask-and-listen",
        "name": "Ask and Listen",
        "rule_ids": ["ask-follow-up-questions", "dont-multitask"],
        "scenario_id": None,
        "created_at": datetime(2026, 9, 22, tzinfo=UTC),
    }
    defaults.update(overrides)
    return Lesson(**defaults)  # type: ignore[arg-type]


def test_create_writes_a_readable_yaml_file(settings: Settings) -> None:
    repo_lessons.create(settings, _lesson())

    path = repo_lessons.lesson_yaml_path(settings, "ask-and-listen")
    assert path.exists()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["id"] == "ask-and-listen"
    assert data["rule_ids"] == ["ask-follow-up-questions", "dont-multitask"]
    assert data["scenario_id"] is None


def test_get_missing_returns_none(settings: Settings) -> None:
    assert repo_lessons.get(settings, "does-not-exist") is None


def test_get_round_trips(settings: Settings) -> None:
    lesson = _lesson()
    repo_lessons.create(settings, lesson)

    fetched = repo_lessons.get(settings, "ask-and-listen")
    assert fetched is not None
    assert fetched.id == lesson.id
    assert fetched.name == lesson.name
    assert fetched.rule_ids == lesson.rule_ids


def test_list_all_on_missing_directory_returns_empty(settings: Settings) -> None:
    assert repo_lessons.list_all(settings) == []


def test_list_all_reads_every_yaml_file(settings: Settings) -> None:
    repo_lessons.create(settings, _lesson(id="lesson-a", name="A"))
    repo_lessons.create(settings, _lesson(id="lesson-b", name="B"))

    assert {lesson.id for lesson in repo_lessons.list_all(settings)} == {"lesson-a", "lesson-b"}


def test_a_hand_edit_to_the_yaml_file_is_picked_up_immediately(settings: Settings) -> None:
    repo_lessons.create(settings, _lesson())
    path = repo_lessons.lesson_yaml_path(settings, "ask-and-listen")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["name"] = "Hand-Edited Name"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    fetched = repo_lessons.get(settings, "ask-and-listen")
    assert fetched is not None
    assert fetched.name == "Hand-Edited Name"
