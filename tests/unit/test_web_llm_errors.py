from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.web.app import create_app
from smalltobig.web.llm_errors import describe
from smalltobig.web.routes import debrief as debrief_routes
from smalltobig.web.routes import status as status_routes

if TYPE_CHECKING:
    from pathlib import Path

DEAD_URL = "http://127.0.0.1:1/v1"  # nothing listens on port 1


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None, data_dir=tmp_path / "data", llm_base_url=DEAD_URL
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def test_a_dead_model_server_gives_a_helpful_page_not_a_bare_500(client: TestClient) -> None:
    response = client.post("/prep", data={"event": "a party"})

    assert response.status_code == 503
    page = html.unescape(response.text)
    assert "isn't running" in page
    assert "mlx_lm.server --model" in page
    assert "--port 1" in page
    assert DEAD_URL in page
    assert "still available" in page


def test_pages_that_do_not_need_the_model_still_work(client: TestClient) -> None:
    assert client.get("/rules").status_code == 200
    assert client.get("/home").status_code == 200


def test_a_slow_model_is_reported_as_slow(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def slow(*args: Any, **kwargs: Any) -> None:
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(debrief_routes, "generate_prep_card", slow)
    response = client.post("/prep", data={"event": "a party"})
    assert response.status_code == 503
    assert "took too long to answer" in response.text


def test_a_model_error_status_is_reported_with_its_code(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(*args: Any, **kwargs: Any) -> None:
        raise httpx.HTTPStatusError(
            "bad", request=httpx.Request("POST", DEAD_URL), response=httpx.Response(500)
        )

    monkeypatch.setattr(debrief_routes, "generate_prep_card", failing)
    response = client.post("/prep", data={"event": "a party"})
    assert response.status_code == 503
    assert "HTTP 500" in response.text


def test_describe_distinguishes_the_failure_kinds() -> None:
    assert describe(httpx.ConnectError("x"))[0] == "isn't running"
    assert describe(httpx.ConnectTimeout("x"))[0] == "isn't running"
    assert describe(httpx.ReadTimeout("x"))[0] == "took too long to answer"
    assert describe(httpx.HTTPError("x"))[0] == "couldn't be reached"


def test_status_pill_says_offline_when_nothing_answers(client: TestClient) -> None:
    page = client.get("/status/model").text
    assert "model offline" in page
    assert "model online" not in page


def test_status_pill_says_online_when_the_server_answers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Up:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def health(self) -> bool:
            return True

        def __enter__(self) -> _Up:
            return self

        def __exit__(self, *exc: object) -> None:
            pass

    monkeypatch.setattr(status_routes, "OpenAICompatClient", _Up)
    assert "model online" in client.get("/status/model").text


def test_every_page_polls_the_status_pill(client: TestClient) -> None:
    assert 'hx-get="/status/model"' in client.get("/rules").text
