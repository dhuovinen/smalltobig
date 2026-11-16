from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.web.app import create_app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]
    return TestClient(create_app(settings))


def test_index_redirects_to_sources(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/sources"


def test_empty_sources_list(client: TestClient) -> None:
    response = client.get("/sources")
    assert response.status_code == 200
    assert "Nothing ingested yet." in response.text


def test_new_source_form_renders(client: TestClient) -> None:
    response = client.get("/sources/new")
    assert response.status_code == 200
    assert "<form" in response.text


def test_create_source_then_view_it(client: TestClient) -> None:
    response = client.post(
        "/sources",
        data={
            "title": "A Pasted Source",
            "author": "Jane Doe",
            "kind": "article",
            "url": "",
            "license_note": "",
            "text": "Some pasted content.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail_url = response.headers["location"]

    detail = client.get(detail_url)
    assert detail.status_code == 200
    assert "A Pasted Source" in detail.text
    assert "Some pasted content." in detail.text

    listing = client.get("/sources")
    assert "A Pasted Source" in listing.text


def test_create_duplicate_source_rerenders_form_with_error(client: TestClient) -> None:
    payload = {
        "title": "First",
        "author": "",
        "kind": "notes",
        "url": "",
        "license_note": "",
        "text": "Identical content.",
    }
    client.post("/sources", data=payload, follow_redirects=False)

    second = dict(payload, title="Second")
    response = client.post("/sources", data=second, follow_redirects=False)

    assert response.status_code == 409
    assert "already ingested" in response.text


def test_source_detail_404_for_unknown_id(client: TestClient) -> None:
    response = client.get("/sources/does-not-exist")
    assert response.status_code == 404


def test_poll_inbox_ingests_dropped_files(client: TestClient, tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]
    settings.inbox_dir.mkdir(parents=True)
    (settings.inbox_dir / "dropped.txt").write_text("Dropped content.", encoding="utf-8")

    response = client.post("/sources/poll-inbox")

    assert response.status_code == 200
    assert "Ingested 1 source(s)" in response.text
    assert "dropped" in response.text
