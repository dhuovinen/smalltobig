"""LlmClient backed by any OpenAI-compatible chat endpoint.

Targets mlx_lm.server by default, but the same client works against Ollama
(`:11434/v1`) or LM Studio (`:1234/v1`) — just point `STB_LLM_BASE_URL` at it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from smalltobig.llm.client import ChatMessage


class OpenAICompatClient:
    def __init__(self, base_url: str, model: str = "", timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.Client(timeout=timeout)

    def health(self) -> bool:
        # mlx_lm.server exposes /health on the server root, not under /v1.
        root = self._base_url.removesuffix("/v1")
        try:
            response = self._client.get(f"{root}/health")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> str:
        payload: dict[str, object] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if self._model:
            # mlx_lm.server treats a present "model" as a repo id to load,
            # rather than a label — omit it to mean "whatever's running".
            payload["model"] = self._model
        response = self._client.post(f"{self._base_url}/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return str(content)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenAICompatClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
