from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.store import db, repo_lessons, repo_rules
from smalltobig.web.app import create_app

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 9, 22, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None, data_dir=tmp_path / "data", repo_root=tmp_path / "repo"
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def _seed_lesson_with_rule(settings: Settings) -> None:
    conn = db.connect(settings.db_path)
    try:
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
                rubric=[RubricItem(id="x", check="Did X?")],
                created_at=NOW,
            ),
        )
    finally:
        conn.close()
    from smalltobig.models.lesson import Lesson

    repo_lessons.create(
        settings,
        Lesson(
            id="ask-and-listen",
            name="Ask and Listen",
            rule_ids=["ask-follow-up-questions"],
            created_at=NOW,
        ),
    )


def test_lessons_list_empty_state(client: TestClient) -> None:
    response = client.get("/lessons")
    assert response.status_code == 200
    assert "No lessons yet" in response.text


def test_lessons_list_shows_seeded_lesson(client: TestClient, settings: Settings) -> None:
    _seed_lesson_with_rule(settings)
    response = client.get("/lessons")
    assert response.status_code == 200
    assert "Ask and Listen" in response.text


def test_lesson_detail_404_for_unknown_lesson(client: TestClient) -> None:
    response = client.get("/lessons/does-not-exist")
    assert response.status_code == 404


def test_lesson_detail_shows_its_rules(client: TestClient, settings: Settings) -> None:
    _seed_lesson_with_rule(settings)
    response = client.get("/lessons/ask-and-listen")
    assert response.status_code == 200
    assert "Ask follow-up questions" in response.text
    assert "Start roleplay" in response.text
