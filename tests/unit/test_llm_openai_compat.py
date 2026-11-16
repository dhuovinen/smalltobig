"""OpenAICompatClient against a fake transport — no real server involved.

Regression coverage for one sharp edge: mlx_lm.server treats a present
"model" field as a repo id to *load*, not a label, so an empty/default model
name must be omitted from the request entirely (see docs/DECISIONS.md #2 and
the 404 this produced against a real server before the fix).
"""

from __future__ import annotations

import json

import httpx
import pytest

from smalltobig.llm.openai_compat import OpenAICompatClient


def _client_with_transport(handler: httpx.MockTransport, **kwargs: object) -> OpenAICompatClient:
    client = OpenAICompatClient("http://127.0.0.1:3140/v1", **kwargs)  # type: ignore[arg-type]
    client._client = httpx.Client(transport=handler)
    return client


def test_health_checks_server_root_not_v1() -> None:
    seen_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(200, json={"status": "ok"})

    client = _client_with_transport(httpx.MockTransport(handler))
    assert client.health() is True
    assert seen_paths == ["/health"]


def test_health_falls_back_to_models_listing() -> None:
    # Ollama has no /health; its OpenAI-compatible /v1/models proves it is up.
    seen_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"object": "list", "data": []})
        return httpx.Response(404)

    client = _client_with_transport(httpx.MockTransport(handler))
    assert client.health() is True
    assert seen_paths == ["/health", "/v1/models"]


def test_health_false_when_neither_route_answers() -> None:
    client = _client_with_transport(httpx.MockTransport(lambda _r: httpx.Response(404)))
    assert client.health() is False


def test_health_returns_false_on_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = _client_with_transport(httpx.MockTransport(handler))
    assert client.health() is False


def test_chat_omits_model_field_when_unset() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "Pong!"}}]},
        )

    client = _client_with_transport(httpx.MockTransport(handler))
    reply = client.chat([{"role": "user", "content": "say pong"}])

    assert reply == "Pong!"
    assert "model" not in bodies[0]


def test_chat_includes_model_field_when_set() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "hi"}}]},
        )

    client = _client_with_transport(httpx.MockTransport(handler), model="some-repo/model")
    client.chat([{"role": "user", "content": "hello"}])

    assert bodies[0]["model"] == "some-repo/model"


def test_chat_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    client = _client_with_transport(httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        client.chat([{"role": "user", "content": "hello"}])
