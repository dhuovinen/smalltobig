"""`stb doctor` and `stb ingest`'s CLI wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from click.testing import CliRunner

from smalltobig import cli
from smalltobig.doctor import CheckResult

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_doctor_exits_zero_when_all_checks_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "run_doctor",
        lambda settings: [CheckResult("llm server", True, "reachable")],
    )
    result = CliRunner().invoke(cli.main, ["doctor"])
    assert result.exit_code == 0


def test_doctor_exits_nonzero_when_a_check_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "run_doctor",
        lambda settings: [CheckResult("llm server", False, "not reachable")],
    )
    result = CliRunner().invoke(cli.main, ["doctor"])
    assert result.exit_code == 1


def test_ingest_picks_up_a_dropped_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STB_DATA_DIR", str(tmp_path))
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "my-notes.txt").write_text("Some notes.", encoding="utf-8")

    result = CliRunner().invoke(cli.main, ["ingest"])

    assert result.exit_code == 0
    assert "my-notes" in result.output
    assert "1 source(s) ingested" in result.output
    assert not (inbox / "my-notes.txt").exists()


def test_ingest_reports_zero_when_inbox_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STB_DATA_DIR", str(tmp_path))

    result = CliRunner().invoke(cli.main, ["ingest"])

    assert result.exit_code == 0
    assert "0 source(s) ingested" in result.output
