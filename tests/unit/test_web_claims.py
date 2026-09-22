from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.extract import pipeline as extract_pipeline
from smalltobig.web.app import create_app
from smalltobig.web.routes import claims as claims_routes

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def _ingest_a_source(client: TestClient) -> str:
    response = client.post(
        "/sources",
        data={
            "title": "A Source",
            "author": "",
            "kind": "notes",
            "url": "",
            "license_note": "",
            "text": "Ask follow-up questions.",
        },
        follow_redirects=False,
    )
    location = response.headers["location"]
    return location.rsplit("/", 1)[-1]


def test_claims_404_for_unknown_source(client: TestClient) -> None:
    response = client.get("/sources/does-not-exist/claims")
    assert response.status_code == 404


def test_claims_empty_state(client: TestClient) -> None:
    source_id = _ingest_a_source(client)
    response = client.get(f"/sources/{source_id}/claims")
    assert response.status_code == 200
    assert "No claims extracted yet." in response.text
    assert "Extract claims" in response.text


def test_extract_route_runs_pipeline_and_redirects_to_claims(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_id = _ingest_a_source(client)

    def fake_extract_source(conn: object, settings: object, llm_client: object, sid: str):  # type: ignore[no-untyped-def]
        return extract_pipeline.ExtractionSummary(
            source_id=sid, chunks=1, proposed=1, accepted=1, rejected=0
        )

    monkeypatch.setattr(claims_routes, "extract_source", fake_extract_source)

    response = client.post(f"/sources/{source_id}/extract", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/sources/{source_id}/claims"


def test_extract_route_404_for_unknown_source(client: TestClient) -> None:
    response = client.post("/sources/does-not-exist/extract")
    assert response.status_code == 404
