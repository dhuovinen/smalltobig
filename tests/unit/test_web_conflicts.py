from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.models.conflict import Conflict, ConflictStatus
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.store import db, repo_conflicts, repo_rules
from smalltobig.web.app import create_app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None, data_dir=tmp_path / "data", repo_root=tmp_path / "repo"
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def _rule(rule_id: str, name: str) -> Rule:
    return Rule(
        id=rule_id,
        name=name,
        imperative=f"{name}.",
        rationale="r",
        when_to_apply="w",
        antipattern="a",
        evidence_tier="C",
        status=RuleStatus.CANDIDATE,
        claims=["clm_1"],
        rubric=[RubricItem(id="x", check="Did X?")],
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
    )


def _seed_conflict(settings: Settings) -> None:
    conn = db.connect(settings.db_path)
    try:
        repo_rules.create(conn, _rule("rule-a", "Rule A"))
        repo_rules.create(conn, _rule("rule-b", "Rule B"))
        repo_conflicts.create(
            conn,
            Conflict(
                id="cfl_1",
                between=["rule-a", "rule-b"],
                note="They contradict.",
                status=ConflictStatus.PROPOSED,
                proposed_resolution="Scope both.",
                created_at=datetime(2026, 9, 22, tzinfo=UTC),
            ),
        )
    finally:
        conn.close()


def test_conflicts_list_empty_state(client: TestClient) -> None:
    response = client.get("/conflicts")
    assert response.status_code == 200
    assert "No conflicts proposed yet." in response.text


def test_conflicts_list_shows_rule_names_and_note(
    client: TestClient, settings: Settings
) -> None:
    _seed_conflict(settings)
    response = client.get("/conflicts")
    assert response.status_code == 200
    assert "Rule A" in response.text
    assert "Rule B" in response.text
    assert "They contradict." in response.text


def test_resolve_conflict_404_for_unknown_conflict(client: TestClient) -> None:
    response = client.post("/conflicts/does-not-exist/resolve", data={"resolution": "Keep both."})
    assert response.status_code == 404


def test_resolve_conflict_records_the_human_resolution(
    client: TestClient, settings: Settings
) -> None:
    _seed_conflict(settings)

    response = client.post(
        "/conflicts/cfl_1/resolve",
        data={"resolution": "Keep both, scoped differently."},
        follow_redirects=False,
    )
    assert response.status_code == 303

    conn = db.connect(settings.db_path)
    try:
        conflict = repo_conflicts.get(conn, "cfl_1")
    finally:
        conn.close()
    assert conflict is not None
    assert conflict.status.value == "resolved"
    assert conflict.resolution == "Keep both, scoped differently."
