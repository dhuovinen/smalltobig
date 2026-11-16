from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.models.mastery import Mastery
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.store import db, repo_mastery, repo_rules
from smalltobig.web.app import create_app
from smalltobig.web.routes import debrief as debrief_routes

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 9, 22, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def _seed_rule(settings: Settings, rule_id: str, score: float = 0.0) -> None:
    conn = db.connect(settings.db_path)
    try:
        repo_rules.create(
            conn,
            Rule(
                id=rule_id,
                name=rule_id,
                imperative=f"{rule_id}.",
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
        repo_mastery.upsert(conn, Mastery(rule_id=rule_id, score=score, updated_at=NOW))
    finally:
        conn.close()


def test_new_prep_card_form_renders(client: TestClient) -> None:
    response = client.get("/prep/new")
    assert response.status_code == 200
    assert "<form" in response.text


def test_create_prep_card_shows_weakest_rules_and_content(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_rule(settings, "weak-rule", score=0.0)
    _seed_rule(settings, "strong-rule", score=9.0)

    def fake_generate(llm_client, event):  # type: ignore[no-untyped-def]
        from smalltobig.practice.debrief import ProposedPrepCard

        return ProposedPrepCard(topics=["topic one", "topic two"], exit_line="Great chat!")

    monkeypatch.setattr(debrief_routes, "generate_prep_card", fake_generate)

    response = client.post("/prep", data={"event": "a work mixer"})

    assert response.status_code == 200
    assert response.text.index("weak-rule") < response.text.index("strong-rule")
    assert "topic one" in response.text
    assert "Great chat!" in response.text


def test_create_prep_card_handles_a_failed_generation(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_rule(settings, "some-rule")
    monkeypatch.setattr(debrief_routes, "generate_prep_card", lambda llm_client, event: None)

    response = client.post("/prep", data={"event": "a work mixer"})

    assert response.status_code == 200
    assert "Couldn't generate topics" in response.text


def test_new_debrief_form_renders(client: TestClient) -> None:
    response = client.get("/debrief/new")
    assert response.status_code == 200
    assert "<form" in response.text


def test_create_debrief_shows_extracted_field_notes(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_rule(settings, "ask-follow-up-questions")

    def fake_submit(conn, llm_client, text):  # type: ignore[no-untyped-def]
        from smalltobig.models.field_note import Debrief, FieldNote

        debrief = Debrief(id="dbf_test", text=text, created_at=NOW)
        note = FieldNote(
            id="fn_test",
            debrief_id="dbf_test",
            rule_id="ask-follow-up-questions",
            quote="what was the best part",
            success=True,
            created_at=NOW,
        )
        return debrief, [note]

    monkeypatch.setattr(debrief_routes, "submit_debrief", fake_submit)

    response = client.post("/debrief", data={"text": "It went well."})

    assert response.status_code == 200
    assert "1 field note(s) extracted" in response.text
    assert "what was the best part" in response.text


def test_field_notes_list_empty_state(client: TestClient) -> None:
    response = client.get("/field-notes")
    assert response.status_code == 200
    assert "No field notes yet" in response.text
