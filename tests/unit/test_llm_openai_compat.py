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


def _recording_client(captured: list[httpx.Request], reply: dict[str, object],
                      **kwargs: object) -> OpenAICompatClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=reply)

    client = OpenAICompatClient("http://127.0.0.1:8090/v1", **kwargs)  # type: ignore[arg-type]
    headers = client._client.headers
    client._client = httpx.Client(transport=httpx.MockTransport(handler), headers=headers)
    return client


OK_REPLY = {"choices": [{"message": {"content": "hi"}}]}


def test_api_key_is_sent_as_bearer_on_every_request() -> None:
    seen: list[httpx.Request] = []
    client = _recording_client(seen, OK_REPLY, api_key="test-key-123")
    client.chat([{"role": "user", "content": "x"}])
    client.health()
    assert seen and all(r.headers["authorization"] == "Bearer test-key-123" for r in seen)


def test_no_authorization_header_without_a_key() -> None:
    seen: list[httpx.Request] = []
    _recording_client(seen, OK_REPLY).chat([{"role": "user", "content": "x"}])
    assert "authorization" not in seen[0].headers


@pytest.mark.parametrize(("setting", "expected"), [(False, False), (True, True)])
def test_thinking_switch_is_sent_when_set(setting: bool, expected: bool) -> None:
    seen: list[httpx.Request] = []
    _recording_client(seen, OK_REPLY, enable_thinking=setting).chat(
        [{"role": "user", "content": "x"}])
    body = json.loads(seen[0].content)
    assert body["chat_template_kwargs"] == {"enable_thinking": expected}


def test_thinking_switch_omitted_by_default() -> None:
    seen: list[httpx.Request] = []
    _recording_client(seen, OK_REPLY).chat([{"role": "user", "content": "x"}])
    assert "chat_template_kwargs" not in json.loads(seen[0].content)


def test_null_content_is_empty_not_the_string_none() -> None:
    seen: list[httpx.Request] = []
    reply = {"choices": [{"message": {"content": None, "reasoning": "thinking..."}}]}
    assert _recording_client(seen, reply).chat([{"role": "user", "content": "x"}]) == ""


def test_settings_carry_the_key_without_ever_showing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    from smalltobig.config import Settings

    monkeypatch.setenv("STB_LLM_API_KEY", "secret-abc-999")
    monkeypatch.setenv("STB_LLM_ENABLE_THINKING", "false")
    monkeypatch.setenv("STB_LLM_TIMEOUT", "120")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    options = settings.llm_options()
    assert options["api_key"] == "secret-abc-999"
    assert options["enable_thinking"] is False and options["timeout"] == 120.0
    assert settings.llm_options(timeout=2.0)["timeout"] == 2.0
    for text in (repr(settings), str(settings), settings.model_dump_json()):
        assert "secret-abc-999" not in text
