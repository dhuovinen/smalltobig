from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.models.claim import Claim, ClaimStatus, ClaimType
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.models.source import Source, SourceKind
from smalltobig.store import db, repo_claims, repo_rules, repo_sources
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


def _seed_rule(settings: Settings, **overrides: object) -> Rule:
    conn = db.connect(settings.db_path)
    try:
        if repo_sources.get(conn, "src_1") is None:
            repo_sources.create(
                conn,
                Source(
                    id="src_1",
                    title="Source",
                    kind=SourceKind.NOTES,
                    retrieved_at=datetime(2026, 9, 22, tzinfo=UTC),
                    sha256="a" * 64,
                ),
                raw_extension=".txt",
            )
        if not repo_claims.get_many(conn, ["clm_1"]):
            repo_claims.create(
                conn,
                Claim(
                    id="clm_1",
                    source_id="src_1",
                    chunk_index=0,
                    verbatim="Ask follow-up questions.",
                    paraphrase="Follow up.",
                    claim_type=ClaimType.EMPIRICAL_FINDING,
                    status=ClaimStatus.ACCEPTED,
                    start=0,
                    end=10,
                    created_at=datetime(2026, 9, 22, tzinfo=UTC),
                ),
            )
        defaults: dict[str, object] = {
            "id": "ask-follow-up-questions",
            "name": "Ask follow-up questions",
            "imperative": "Ask about what they just said.",
            "rationale": "Follow-ups signal responsiveness.",
            "when_to_apply": "Past the opening two turns.",
            "antipattern": "Changing the subject.",
            "evidence_tier": "A",
            "status": RuleStatus.CANDIDATE,
            "claims": ["clm_1"],
            "rubric": [RubricItem(id="asked_followup", check="Did you ask a follow-up?")],
            "created_at": datetime(2026, 9, 22, tzinfo=UTC),
        }
        defaults.update(overrides)
        rule = Rule(**defaults)  # type: ignore[arg-type]
        repo_rules.create(conn, rule)
        return rule
    finally:
        conn.close()


def test_rules_list_empty_state(client: TestClient) -> None:
    response = client.get("/rules")
    assert response.status_code == 200
    assert "No rules yet" in response.text


def test_rules_list_shows_seeded_rule(client: TestClient, settings: Settings) -> None:
    _seed_rule(settings)
    response = client.get("/rules")
    assert response.status_code == 200
    assert "Ask follow-up questions" in response.text


def test_rule_detail_404_for_unknown_rule(client: TestClient) -> None:
    response = client.get("/rules/does-not-exist")
    assert response.status_code == 404


def test_rule_detail_shows_provenance(client: TestClient, settings: Settings) -> None:
    _seed_rule(settings)
    response = client.get("/rules/ask-follow-up-questions")
    assert response.status_code == 200
    assert "Ask follow-up questions." in response.text
    assert "src_1" in response.text


def test_accept_rule_writes_yaml_and_redirects(client: TestClient, settings: Settings) -> None:
    _seed_rule(settings)

    response = client.post(
        "/rules/ask-follow-up-questions/accept", follow_redirects=False
    )

    assert response.status_code == 303
    conn = db.connect(settings.db_path)
    try:
        rule = repo_rules.get(conn, "ask-follow-up-questions")
    finally:
        conn.close()
    assert rule is not None
    assert rule.status.value == "accepted"

    from smalltobig.store import yaml_sync

    assert yaml_sync.rule_yaml_path(settings, "ask-follow-up-questions").exists()


def test_reject_rule_removes_yaml_if_previously_accepted(
    client: TestClient, settings: Settings
) -> None:
    _seed_rule(settings, status=RuleStatus.ACCEPTED)
    from smalltobig.store import yaml_sync

    conn = db.connect(settings.db_path)
    try:
        rule = repo_rules.get(conn, "ask-follow-up-questions")
        assert rule is not None
        yaml_sync.write_rule(settings, rule)
    finally:
        conn.close()
    assert yaml_sync.rule_yaml_path(settings, "ask-follow-up-questions").exists()

    client.post("/rules/ask-follow-up-questions/reject", follow_redirects=False)

    assert not yaml_sync.rule_yaml_path(settings, "ask-follow-up-questions").exists()


def test_supersede_rule_requires_a_valid_target(client: TestClient, settings: Settings) -> None:
    _seed_rule(settings)
    response = client.post(
        "/rules/ask-follow-up-questions/supersede",
        data={"superseded_by": "does-not-exist"},
    )
    assert response.status_code == 400


def test_supersede_rule_updates_status_and_target(
    client: TestClient, settings: Settings
) -> None:
    _seed_rule(settings)
    _seed_rule(settings, id="newer-rule", name="Newer rule")

    response = client.post(
        "/rules/ask-follow-up-questions/supersede",
        data={"superseded_by": "newer-rule"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    conn = db.connect(settings.db_path)
    try:
        rule = repo_rules.get(conn, "ask-follow-up-questions")
    finally:
        conn.close()
    assert rule is not None
    assert rule.status.value == "superseded"
    assert rule.superseded_by == "newer-rule"
