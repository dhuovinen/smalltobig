"""`stb doctor` — reach the chat server, round-trip a generation, load the
embedding model, embed two strings and report their cosine similarity.

Nothing else gets built until this is green — see docs/PLAN.md §5 Phase 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from smalltobig.llm.openai_compat import OpenAICompatClient

if TYPE_CHECKING:
    from collections.abc import Callable

    from smalltobig.config import Settings
    from smalltobig.llm.client import LlmClient


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def check_llm_health(client: LlmClient) -> CheckResult:
    ok = client.health()
    return CheckResult("llm server", ok, "reachable" if ok else "not reachable")


def check_llm_generation(client: LlmClient) -> CheckResult:
    try:
        reply = client.chat(
            [{"role": "user", "content": "Reply with exactly one word: pong"}],
            max_tokens=8,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a check result, not a crash
        return CheckResult("llm generation", False, f"request failed: {exc}")
    reply = reply.strip()
    return CheckResult("llm generation", bool(reply), repr(reply) if reply else "empty reply")


def _real_embed_two(repo_id: str) -> float:
    # Imported lazily: the `mlx` extra is Apple Silicon only and absent from
    # CI, so this import must not run at module scope (docs/PLAN.md §6).
    from smalltobig.embed.mlx_backend import EmbeddingModel, cosine_similarity

    model = EmbeddingModel(repo_id)
    embeddings = model.embed(["I like grapes", "I like fruits"])
    return cosine_similarity(embeddings[0], embeddings[1])


def check_embeddings(
    repo_id: str, embed_two: Callable[[str], float] = _real_embed_two
) -> CheckResult:
    try:
        similarity = embed_two(repo_id)
    except ImportError as exc:
        return CheckResult(
            "embedding model",
            False,
            f"mlx-embeddings not installed ({exc}); "
            "run `pip install -e '.[mlx]'` (Apple Silicon only)",
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a check result, not a crash
        return CheckResult("embedding model", False, f"failed: {exc}")
    return CheckResult("embedding model", True, f"cosine similarity = {similarity:.4f}")


def run_doctor(settings: Settings) -> list[CheckResult]:
    with OpenAICompatClient(settings.llm_base_url, **settings.llm_options()) as client:
        results = [check_llm_health(client), check_llm_generation(client)]
    results.append(check_embeddings(settings.embedding_model))
    return results
