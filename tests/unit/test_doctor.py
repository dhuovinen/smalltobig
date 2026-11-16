"""stb doctor's individual checks, without a real model server or the mlx
extra installed — see docs/PLAN.md §5 Phase 0 for what each check proves."""

from __future__ import annotations

from typing import TYPE_CHECKING

from smalltobig.doctor import check_embeddings, check_llm_generation, check_llm_health

if TYPE_CHECKING:
    from smalltobig.llm.client import ChatMessage


class _FakeClient:
    def __init__(self, *, healthy: bool = True, reply: str = "Pong!") -> None:
        self._healthy = healthy
        self._reply = reply

    def health(self) -> bool:
        return self._healthy

    def chat(
        self, messages: list[ChatMessage], *, max_tokens: int = 256, temperature: float = 0.0
    ) -> str:
        return self._reply


def test_check_llm_health_ok() -> None:
    result = check_llm_health(_FakeClient(healthy=True))
    assert result.ok
    assert result.name == "llm server"


def test_check_llm_health_unreachable() -> None:
    result = check_llm_health(_FakeClient(healthy=False))
    assert not result.ok


def test_check_llm_generation_ok() -> None:
    result = check_llm_generation(_FakeClient(reply="Pong!"))
    assert result.ok
    assert "Pong!" in result.detail


def test_check_llm_generation_empty_reply_fails() -> None:
    result = check_llm_generation(_FakeClient(reply="   "))
    assert not result.ok


def test_check_llm_generation_reports_request_failure() -> None:
    class _RaisingClient:
        def health(self) -> bool:
            return True

        def chat(
            self, messages: list[ChatMessage], *, max_tokens: int = 256, temperature: float = 0.0
        ) -> str:
            raise RuntimeError("connection refused")

    result = check_llm_generation(_RaisingClient())
    assert not result.ok
    assert "connection refused" in result.detail


def test_check_embeddings_ok_with_injected_backend() -> None:
    result = check_embeddings("some/repo", embed_two=lambda repo_id: 0.77)
    assert result.ok
    assert "0.77" in result.detail


def test_check_embeddings_reports_missing_mlx_extra() -> None:
    def missing(repo_id: str) -> float:
        raise ImportError("No module named 'mlx_embeddings'")

    result = check_embeddings("some/repo", embed_two=missing)
    assert not result.ok
    assert "mlx" in result.detail.lower()


def test_check_embeddings_reports_other_failures() -> None:
    def broken(repo_id: str) -> float:
        raise RuntimeError("model download failed")

    result = check_embeddings("some/repo", embed_two=broken)
    assert not result.ok
    assert "model download failed" in result.detail
