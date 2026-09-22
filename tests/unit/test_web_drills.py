from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.store import db, repo_rules
from smalltobig.web.app import create_app
from smalltobig.web.routes import drills as drills_routes

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 9, 22, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def _seed_rule(settings: Settings) -> None:
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


def test_new_drill_404_for_unknown_rule(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(drills_routes, "generate_stimulus", lambda client, rule: "unused")
    response = client.get("/rules/does-not-exist/drill")
    assert response.status_code == 404


def test_new_drill_shows_a_generated_stimulus(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_rule(settings)
    monkeypatch.setattr(
        drills_routes, "generate_stimulus", lambda client, rule: "I just got back from Japan."
    )

    response = client.get("/rules/ask-follow-up-questions/drill")

    assert response.status_code == 200
    assert "I just got back from Japan." in response.text


def test_submit_drill_shows_results(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_rule(settings)

    def fake_score_drill(  # type: ignore[no-untyped-def]
        conn: object, llm_client: object, rule_id: str, stimulus: str, response: str
    ):
        from smalltobig.models.drill import Drill, RubricResult

        return Drill(
            id="drl_test",
            rule_id=rule_id,
            stimulus=stimulus,
            response=response,
            rubric_results=[RubricResult(rubric_id="asked_followup", passed=True, quote="ok")],
            success=True,
            created_at=NOW,
        )

    monkeypatch.setattr(drills_routes, "score_drill", fake_score_drill)

    response = client.post(
        "/rules/ask-follow-up-questions/drill",
        data={"stimulus": "They say hi.", "response": "What's new with you?"},
    )

    assert response.status_code == 200
    assert "passed" in response.text
    assert "Did you ask a follow-up?" in response.text


def test_submit_drill_404_for_unknown_rule(client: TestClient) -> None:
    response = client.post(
        "/rules/does-not-exist/drill", data={"stimulus": "x", "response": "y"}
    )
    assert response.status_code == 404
