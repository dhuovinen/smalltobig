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

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 9, 22, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def test_mastery_empty_state(client: TestClient) -> None:
    response = client.get("/mastery")
    assert response.status_code == 200
    assert "No accepted rules yet." in response.text


def test_mastery_shows_weakest_rule_first(client: TestClient, settings: Settings) -> None:
    conn = db.connect(settings.db_path)
    try:
        for rule_id, score in [("strong-rule", 5.0), ("weak-rule", 0.5)]:
            repo_rules.create(
                conn,
                Rule(
                    id=rule_id,
                    name=rule_id,
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
            repo_mastery.upsert(conn, Mastery(rule_id=rule_id, score=score, updated_at=NOW))
    finally:
        conn.close()

    response = client.get("/mastery")
    assert response.status_code == 200
    assert response.text.index("weak-rule") < response.text.index("strong-rule")


def test_mastery_defaults_a_rule_with_no_recorded_signal_yet(
    client: TestClient, settings: Settings
) -> None:
    conn = db.connect(settings.db_path)
    try:
        repo_rules.create(
            conn,
            Rule(
                id="untested-rule",
                name="untested-rule",
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
    finally:
        conn.close()

    response = client.get("/mastery")
    assert response.status_code == 200
    assert "box 1" in response.text
