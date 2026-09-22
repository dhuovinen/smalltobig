"""`stb doctor`, `stb ingest` and `stb extract`'s CLI wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from smalltobig import cli
from smalltobig.doctor import CheckResult
from smalltobig.extract import pipeline as extract_pipeline
from smalltobig.synth import pipeline as synth_pipeline

if TYPE_CHECKING:
    from pathlib import Path


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


def test_extract_reports_the_rejection_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        extract_pipeline,
        "extract_source",
        lambda conn, settings, client, source_id: extract_pipeline.ExtractionSummary(
            source_id=source_id, chunks=2, proposed=10, accepted=6, rejected=4
        ),
    )

    result = CliRunner().invoke(cli.main, ["extract", "src_example"])

    assert result.exit_code == 0
    assert "2 chunk(s), 10 claim(s) proposed" in result.output
    assert "6 accepted, 4 rejected (40% rejection rate)" in result.output


def test_extract_exits_nonzero_for_an_unknown_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STB_DATA_DIR", str(tmp_path))

    def _raise(conn: object, settings: object, client: object, source_id: str) -> None:
        raise extract_pipeline.UnknownSourceError(source_id)

    monkeypatch.setattr(extract_pipeline, "extract_source", _raise)

    result = CliRunner().invoke(cli.main, ["extract", "src_does_not_exist"])

    assert result.exit_code == 1
    assert "unknown source" in result.output


def test_synthesize_reports_the_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # cli.py imports smalltobig.embed.mlx_backend lazily, only when
    # `synthesize` actually runs — this test needs that module importable
    # (the `mlx` extra) purely to monkeypatch its EmbeddingModel class, not
    # to run any real model. Skip cleanly where the extra isn't installed
    # (e.g. CI) rather than failing test collection for the whole file.
    mlx_backend = pytest.importorskip("smalltobig.embed.mlx_backend")
    monkeypatch.setenv("STB_DATA_DIR", str(tmp_path))

    class _FakeVectors:
        def __init__(self, data: list[list[float]]) -> None:
            self._data = data

        def tolist(self) -> list[list[float]]:
            return self._data

    class _FakeEmbeddingModel:
        def __init__(self, repo_id: str) -> None:
            self.repo_id = repo_id

        def embed(self, texts: list[str]) -> _FakeVectors:
            return _FakeVectors([[1.0, 0.0] for _ in texts])

    monkeypatch.setattr(mlx_backend, "EmbeddingModel", _FakeEmbeddingModel)
    monkeypatch.setattr(
        synth_pipeline,
        "synthesize_rules",
        lambda conn, client, embed: synth_pipeline.SynthesisSummary(
            accepted_claims=5,
            clusters=2,
            rules_drafted=2,
            rules_skipped_existing=0,
            conflict_candidates=1,
            conflicts_proposed=1,
        ),
    )

    result = CliRunner().invoke(cli.main, ["synthesize"])

    assert result.exit_code == 0
    assert "5 accepted claim(s), 2 cluster(s)" in result.output
    assert "2 rule(s) drafted, 0 already covered" in result.output
    assert "1 near-neighbour pair(s) checked, 1 conflict(s) proposed" in result.output
