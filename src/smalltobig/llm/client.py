"""The chat client seam.

Kept as a Protocol so a batch job (Stage 3 synthesis, docs/DECISIONS.md #11)
can swap in a larger or hosted model without touching call sites.
"""

from __future__ import annotations

from typing import Literal, Protocol, TypedDict


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LlmClient(Protocol):
    def health(self) -> bool:
        """Return whether the model server is reachable."""
        ...

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> str:
        """Send a chat completion request and return the reply text."""
        ...
