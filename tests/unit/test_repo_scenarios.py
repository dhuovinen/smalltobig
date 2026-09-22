from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from smalltobig.config import Settings
from smalltobig.store import repo_scenarios

if TYPE_CHECKING:
    from pathlib import Path

SCENARIO_YAML = """
id: test-scenario
name: Test Scenario
setting: A quiet room.
persona:
  name: Alex
  warmth: warm
  verbosity: moderate
  hidden_interest: Alex secretly loves jazz.
  private_instructions: You are Alex. Be warm.
"""


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, repo_root=tmp_path / "repo")  # type: ignore[call-arg]


def _write_scenario(settings: Settings) -> None:
    settings.scenarios_dir.mkdir(parents=True, exist_ok=True)
    (settings.scenarios_dir / "test-scenario.yaml").write_text(
        SCENARIO_YAML, encoding="utf-8"
    )


def test_list_all_on_missing_directory_returns_empty(settings: Settings) -> None:
    assert repo_scenarios.list_all(settings) == []


def test_get_missing_returns_none(settings: Settings) -> None:
    assert repo_scenarios.get(settings, "does-not-exist") is None


def test_get_reads_the_full_scenario(settings: Settings) -> None:
    _write_scenario(settings)
    scenario = repo_scenarios.get(settings, "test-scenario")
    assert scenario is not None
    assert scenario.name == "Test Scenario"
    assert scenario.persona.name == "Alex"
    assert scenario.persona.hidden_interest == "Alex secretly loves jazz."


def test_list_all_finds_every_scenario_file(settings: Settings) -> None:
    _write_scenario(settings)
    scenarios = repo_scenarios.list_all(settings)
    assert [scenario.id for scenario in scenarios] == ["test-scenario"]


def test_real_seed_scenarios_load_without_error() -> None:
    # The actual shipped scenarios/ directory at the repo root.
    from pathlib import Path

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, repo_root=Path(__file__).resolve().parents[2]
    )
    scenarios = repo_scenarios.list_all(settings)
    assert len(scenarios) >= 5
    assert all(scenario.persona.private_instructions for scenario in scenarios)
