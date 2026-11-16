"""Web: /htmsw/profile and /htmsw/prep (IMPLEMENTATION.md Phase 2)."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.web.app import create_app

if TYPE_CHECKING:
    from pathlib import Path

PROFILE = {"has_kids": "yes", "kids_stage": "teen", "caregiving": "no", "primary_focus": "family"}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def test_prep_form_asks_for_a_profile_first(client: TestClient) -> None:
    r = client.get("/htmsw/prep/new")
    assert r.status_code == 200
    assert "/htmsw/profile" in r.text
    assert 'name="domain_id"' not in r.text


def test_prep_without_profile_redirects(client: TestClient) -> None:
    r = client.post("/htmsw/prep", data={"domain_id": "cold_networking"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/htmsw/profile"


def test_profile_form_lists_every_question(client: TestClient) -> None:
    r = client.get("/htmsw/profile")
    assert r.status_code == 200
    for q in ("has_kids", "kids_stage", "caregiving", "primary_focus"):
        assert f'name="{q}"' in r.text


def test_save_profile_then_build_a_card(client: TestClient) -> None:
    r = client.post("/htmsw/profile", data=PROFILE, follow_redirects=False)
    assert r.status_code == 303
    form = client.get("/htmsw/prep/new")
    assert "Family rooted" in form.text
    card = client.post(
        "/htmsw/prep", data={"domain_id": "giving_back", "target_notes": "Runs a food bank"}
    )
    assert card.status_code == 200
    for name in ("Initial disclosure", "Build-on question", "Connecting micro-disclosure",
                 "Earned ask"):
        assert name in card.text
    assert "From what you know about them: Runs a food bank" in card.text
    assert "Principle:" in card.text
    assert "not scripts to read" in card.text


def test_invalid_profile_is_rejected(client: TestClient) -> None:
    r = client.post("/htmsw/profile", data={**PROFILE, "kids_stage": "Ava, age 15"})
    assert r.status_code == 422
    assert "must be one of" in r.text


def test_gap_is_shown_not_hidden(client: TestClient) -> None:
    client.post(
        "/htmsw/profile",
        data={"has_kids": "no", "caregiving": "no", "primary_focus": "professional"},
    )
    card = client.post("/htmsw/prep", data={"domain_id": "potential_collaborator"})
    assert "No curated example yet" in card.text


def test_target_notes_are_never_stored(client: TestClient, settings: Settings) -> None:
    # Scenario data is ephemeral (REQUIREMENTS.md §5): sweep every column of every table.
    sentinel = "SENTINEL-Sarah-Okafor-4410"
    client.post("/htmsw/profile", data=PROFILE)
    client.post("/htmsw/prep", data={"domain_id": "cold_networking", "target_notes": sentinel})
    conn = sqlite3.connect(settings.db_path)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            for row in conn.execute(f"SELECT * FROM {table}"):  # noqa: S608
                assert all(sentinel not in str(v) for v in row), table
    finally:
        conn.close()
