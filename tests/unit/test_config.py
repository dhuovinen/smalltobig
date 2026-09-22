"""Settings load from STB_* env vars and .env, with env vars winning.

See docs/DECISIONS.md #9: .env must auto-load, and an explicit environment
variable must still override the file, or config that "looks right" can
silently be ignored.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from smalltobig.config import Settings

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_defaults_match_decisions_doc() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.port == 3041
    assert settings.llm_base_url == "http://127.0.0.1:3140/v1"
    assert settings.llm_model == ""


def test_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STB_PORT", "9999")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.port == 9999


def test_dot_env_is_auto_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("STB_PORT=4242\n")
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.port == 4242


def test_explicit_env_var_beats_dot_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("STB_PORT=4242\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STB_PORT", "5555")
    settings = Settings()
    assert settings.port == 5555
