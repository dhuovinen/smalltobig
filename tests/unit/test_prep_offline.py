"""NFR-13 / FR-34 acceptance: `stb prep` works with no network and no model server.

Every outbound socket connection is made to fail, STB_LLM_BASE_URL is unset, and
the card must still come out complete. A second test checks statically that the
composition and intake modules import nothing that talks to a model.
"""

from __future__ import annotations

import ast
import socket
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from smalltobig.cli import main

SRC = Path(__file__).resolve().parents[2] / "src" / "smalltobig"
FORBIDDEN_IMPORTS = ("httpx", "requests", "urllib", "openai", "smalltobig.llm", "socket")


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    attempts: list[Any] = []

    def refuse(self: socket.socket, address: Any) -> None:
        attempts.append(address)
        raise OSError("network disabled for this test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: refuse(None, a))  # type: ignore[arg-type]
    return attempts


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STB_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("STB_LLM_MODEL", raising=False)
    monkeypatch.setenv("STB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.chdir(tmp_path)  # no stray .env picked up from the repo


def test_stb_prep_offline_with_cluster(env: None, no_network: list[Any]) -> None:
    result = CliRunner().invoke(
        main, ["prep", "--domain", "giving_back", "--cluster", "purpose_driven"]
    )
    assert result.exit_code == 0, result.output
    for heading in ("1. Initial disclosure", "2. Build-on question",
                    "3. Connecting micro-disclosure", "4. Earned ask"):
        assert heading in result.output
    assert "entirely yours" in result.output
    assert no_network == []


def test_stb_prep_offline_from_saved_profile(env: None, no_network: list[Any]) -> None:
    runner = CliRunner()
    saved = runner.invoke(
        main, ["profile", "set", "has_kids=yes", "kids_stage=teen", "caregiving=no",
               "primary_focus=family"],
    )
    assert saved.exit_code == 0, saved.output
    result = runner.invoke(
        main, ["prep", "--domain", "cold_networking", "--target", "met at a mixer"]
    )
    assert result.exit_code == 0, result.output
    assert "Family rooted" in result.output
    assert "icebreaker" in result.output
    assert no_network == []


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize(
    "module",
    ["prep/compose.py", "intake/classify.py", "intake/profile.py", "framework/loader.py"],
)
def test_prep_path_imports_nothing_that_reaches_a_model(module: str) -> None:
    bad = {
        name for name in _imports(SRC / module)
        if any(name == f or name.startswith(f + ".") for f in FORBIDDEN_IMPORTS)
    }
    assert not bad, f"{module} imports {sorted(bad)}; the prep path must stay offline (FR-34)"
