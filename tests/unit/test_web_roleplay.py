from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.models.lesson import Lesson
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.models.session import Session, SessionRubricResult, Turn
from smalltobig.store import db, repo_lessons, repo_rules, repo_sessions
from smalltobig.web.app import create_app
from smalltobig.web.routes import roleplay as roleplay_routes

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


ELEVATOR_SCENARIO_YAML = """
id: elevator
name: Elevator
setting: A short elevator ride.
persona:
  name: Marcus
  warmth: friendly
  verbosity: terse
  hidden_interest: He loves cycling.
  private_instructions: You are Marcus, a coworker.
"""


@pytest.fixture(autouse=True)
def _seed_scenario(settings: Settings) -> None:
    settings.scenarios_dir.mkdir(parents=True, exist_ok=True)
    (settings.scenarios_dir / "elevator.yaml").write_text(
        ELEVATOR_SCENARIO_YAML, encoding="utf-8"
    )


@pytest.fixture
def lesson_id(settings: Settings) -> str:
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
                rubric=[RubricItem(id="asked_followup", check="Did you ask a follow-up?")],
                created_at=NOW,
            ),
        )
    finally:
        conn.close()
    lesson = Lesson(
        id="ask-and-listen",
        name="Ask and Listen",
        rule_ids=["ask-follow-up-questions"],
        created_at=NOW,
    )
    repo_lessons.create(settings, lesson)
    return lesson.id


def test_new_roleplay_404_for_unknown_lesson(client: TestClient) -> None:
    response = client.get("/lessons/does-not-exist/roleplay/new")
    assert response.status_code == 404


def test_new_roleplay_lists_scenarios(client: TestClient, lesson_id: str) -> None:
    response = client.get(f"/lessons/{lesson_id}/roleplay/new")
    assert response.status_code == 200
    assert "Elevator" in response.text


def test_start_roleplay_404_for_unknown_scenario(client: TestClient, lesson_id: str) -> None:
    response = client.post(
        f"/lessons/{lesson_id}/roleplay/start", data={"scenario_id": "does-not-exist"}
    )
    assert response.status_code == 404


def test_start_roleplay_shows_the_generated_opening_line(
    client: TestClient, lesson_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        roleplay_routes, "generate_opening_line", lambda client, scenario: "Busy day?"
    )

    response = client.post(
        f"/lessons/{lesson_id}/roleplay/start", data={"scenario_id": "elevator"}
    )

    assert response.status_code == 200
    assert "Busy day?" in response.text


def test_continue_roleplay_appends_turns(
    client: TestClient, lesson_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        roleplay_routes, "generate_reply", lambda client, scenario, turns: "Not bad, you?"
    )
    turns_json = json.dumps([{"speaker": "partner", "text": "Busy day?"}])

    response = client.post(
        f"/lessons/{lesson_id}/roleplay/turn",
        data={
            "scenario_id": "elevator",
            "turns_json": turns_json,
            "reply": "Pretty good, thanks!",
        },
    )

    assert response.status_code == 200
    assert "Pretty good, thanks!" in response.text
    assert "Not bad, you?" in response.text


def test_finish_roleplay_redirects_to_the_session(
    client: TestClient, lesson_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_end_session(conn, settings, llm_client, lesson_id, scenario_id, turns):  # type: ignore[no-untyped-def]
        return Session(
            id="ses_test",
            lesson_id=lesson_id,
            scenario_id=scenario_id,
            rule_ids=["ask-follow-up-questions"],
            turns=turns,
            rubric_results=[],
            created_at=NOW,
            ended_at=NOW,
        )

    monkeypatch.setattr(roleplay_routes, "end_roleplay_session", fake_end_session)
    turns_json = json.dumps([{"speaker": "partner", "text": "Busy day?"}])

    response = client.post(
        f"/lessons/{lesson_id}/roleplay/end",
        data={"scenario_id": "elevator", "turns_json": turns_json},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/sessions/ses_test"


def test_sessions_list_empty_state(client: TestClient) -> None:
    response = client.get("/sessions")
    assert response.status_code == 200
    assert "No roleplay sessions yet" in response.text


def test_session_detail_404_for_unknown_session(client: TestClient) -> None:
    response = client.get("/sessions/does-not-exist")
    assert response.status_code == 404


def test_session_detail_shows_transcript_and_rubric(
    client: TestClient, settings: Settings, lesson_id: str
) -> None:
    conn = db.connect(settings.db_path)
    try:
        repo_sessions.create(
            conn,
            Session(
                id="ses_test",
                lesson_id=lesson_id,
                scenario_id="elevator",
                rule_ids=["ask-follow-up-questions"],
                turns=[
                    Turn(speaker="partner", text="Busy day?"),
                    Turn(speaker="user", text="What about you?"),
                ],
                rubric_results=[
                    SessionRubricResult(
                        rule_id="ask-follow-up-questions",
                        rubric_id="asked_followup",
                        passed=True,
                        quote="What about you?",
                    )
                ],
                created_at=NOW,
                ended_at=NOW,
            ),
        )
    finally:
        conn.close()

    response = client.get("/sessions/ses_test")
    assert response.status_code == 200
    assert "What about you?" in response.text
    assert "Marcus" in response.text  # elevator scenario's persona name
