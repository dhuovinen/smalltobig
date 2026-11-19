"""LlmClient backed by any OpenAI-compatible chat endpoint.

Targets mlx_lm.server by default, but the same client works against Ollama
(`:11434/v1`), LM Studio (`:1234/v1`) or omlx-serve — point `STB_LLM_BASE_URL` at
it, and set `STB_LLM_API_KEY` if the server requires a key. Build it from
`settings.llm_options()` so every call site gets the same configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from smalltobig.llm.client import ChatMessage


class OpenAICompatClient:
    def __init__(
        self,
        base_url: str,
        model: str = "",
        timeout: float = 30.0,
        api_key: str = "",
        enable_thinking: bool | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._enable_thinking = enable_thinking
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(timeout=timeout, headers=headers)

    def health(self) -> bool:
        # mlx_lm.server exposes /health on the server root, not under /v1. Ollama
        # and most other OpenAI-compatible servers have no such route, so fall
        # back to the standard {base}/models listing before reporting offline
        # (DECISIONS #25: the nav pill said "model offline" while Ollama answered).
        root = self._base_url.removesuffix("/v1")
        for url in (f"{root}/health", f"{self._base_url}/models"):
            try:
                if self._client.get(url).status_code == 200:
                    return True
            except httpx.HTTPError:
                return False
        return False

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
        if self._enable_thinking is not None:
            # Understood by Qwen-family chat templates (mlx, omlx, llama.cpp, vLLM);
            # servers that don't support it ignore the field.
            payload["chat_template_kwargs"] = {"enable_thinking": self._enable_thinking}
        if self._model:
            # mlx_lm.server treats a present "model" as a repo id to load,
            # rather than a label — omit it to mean "whatever's running".
            payload["model"] = self._model
        response = self._client.post(f"{self._base_url}/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"].get("content")
        # A thinking model can answer with content null; never return the string "None".
        return "" if content is None else str(content)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenAICompatClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
