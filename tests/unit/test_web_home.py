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
from smalltobig.store.repo_stats import HomeStats
from smalltobig.web.app import create_app
from smalltobig.web.routes.home import next_move

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 9, 29, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def _stats(**overrides: int) -> HomeStats:
    values = {
        "sources": 0,
        "claims": 0,
        "rules_candidate": 0,
        "rules_accepted": 0,
        "conflicts_open": 0,
        "drills": 0,
        "sessions": 0,
        "field_notes": 0,
    }
    values.update(overrides)
    return HomeStats(**values)


def _rule(status: RuleStatus = RuleStatus.ACCEPTED) -> Rule:
    return Rule(
        id="ask-follow-up-questions",
        name="Ask follow-up questions",
        imperative="Ask about what they just said.",
        rationale="r",
        when_to_apply="w",
        antipattern="a",
        evidence_tier="A",
        status=status,
        claims=["clm_1"],
        rubric=[RubricItem(id="x", check="Did X?")],
        created_at=NOW,
    )


def test_next_move_walks_the_pipeline_in_order() -> None:
    weakest = _rule()
    assert next_move(_stats(), None).href == "/sources/new"
    assert next_move(_stats(sources=1), None).stage == "extract"
    assert "stb synthesize" in next_move(_stats(sources=1, claims=3), None).detail
    assert next_move(_stats(sources=1, claims=3, rules_candidate=2), None).href == "/rules"
    assert (
        next_move(_stats(sources=1, claims=3, rules_accepted=1, conflicts_open=1), weakest).href
        == "/conflicts"
    )
    drill = next_move(_stats(sources=1, claims=3, rules_accepted=1), weakest)
    assert drill.href == "/rules/ask-follow-up-questions/drill"


def test_next_move_pushes_toward_the_real_world_after_drilling() -> None:
    move = next_move(_stats(sources=1, claims=3, rules_accepted=1, drills=4), _rule())
    assert move.stage == "field"
    assert move.href == "/debrief/new"


def test_home_renders_the_empty_state(client: TestClient) -> None:
    response = client.get("/home")
    assert response.status_code == 200
    assert "with receipts" in response.text
    assert "Paste a source" in response.text
    assert "sample" in response.text


def test_home_shows_a_real_receipt_for_an_accepted_rule(
    client: TestClient, settings: Settings
) -> None:
    conn = db.connect(settings.db_path)
    try:
        repo_sources.create(
            conn,
            Source(
                id="src_1",
                title="A Study of Questions",
                author="Someone",
                kind=SourceKind.NOTES,
                retrieved_at=NOW,
                sha256="a" * 64,
            ),
            raw_extension=".txt",
        )
        repo_claims.create(
            conn,
            Claim(
                id="clm_1",
                source_id="src_1",
                chunk_index=0,
                verbatim="Follow-up questions signal listening.",
                paraphrase="Follow-ups signal listening.",
                claim_type=ClaimType.EMPIRICAL_FINDING,
                status=ClaimStatus.ACCEPTED,
                start=0,
                end=10,
                created_at=NOW,
            ),
        )
        repo_rules.create(conn, _rule())
    finally:
        conn.close()

    response = client.get("/home")

    assert response.status_code == 200
    assert "Follow-up questions signal listening." in response.text
    assert "A Study of Questions" in response.text
    assert "Drill your weakest rule" in response.text
    assert "Your rules, by box" in response.text
