"""Integrity checks for the hand-authored scenarios in scenarios/*.yaml.

These run in CI for the same reason tests/test_seed.py does: the actor
prompt in practice/roleplay.py is built directly from these fields, so a
scenario missing a persona field or repeating an id would silently break
roleplay rather than fail at import time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"
REQUIRED_PERSONA_FIELDS = {
    "name",
    "warmth",
    "verbosity",
    "hidden_interest",
    "private_instructions",
}


@pytest.fixture(scope="module")
def scenario_files() -> list[Path]:
    files = sorted(SCENARIOS.glob("*.yaml"))
    assert files, "expected at least one scenario under scenarios/"
    return files


@pytest.fixture(scope="module")
def scenarios(scenario_files: list[Path]) -> list[dict[str, Any]]:
    loaded = []
    for path in scenario_files:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data, dict), path
        loaded.append(data)
    return loaded


def test_filename_matches_the_scenarios_own_id(scenario_files: list[Path]) -> None:
    for path in scenario_files:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert path.stem == data["id"], path


def test_scenario_ids_are_unique(scenarios: list[dict[str, Any]]) -> None:
    ids = [scenario["id"] for scenario in scenarios]
    assert len(ids) == len(set(ids))


def test_every_scenario_has_a_name_and_setting(scenarios: list[dict[str, Any]]) -> None:
    for scenario in scenarios:
        assert scenario.get("name"), scenario["id"]
        assert scenario.get("setting"), scenario["id"]


def test_every_scenario_has_a_complete_persona(scenarios: list[dict[str, Any]]) -> None:
    for scenario in scenarios:
        persona = scenario.get("persona")
        assert isinstance(persona, dict), scenario["id"]
        missing = REQUIRED_PERSONA_FIELDS - persona.keys()
        assert not missing, f"{scenario['id']} persona missing {sorted(missing)}"
        for field in REQUIRED_PERSONA_FIELDS:
            assert persona[field], f"{scenario['id']} persona.{field} is empty"


def test_hidden_interest_is_never_in_the_setting_text(scenarios: list[dict[str, Any]]) -> None:
    """The setting is shown to the practicer before the session starts —
    the hidden interest must not leak into it."""
    for scenario in scenarios:
        hidden = scenario["persona"]["hidden_interest"].strip().rstrip(".")
        # A loose check: the setting shouldn't quote the hidden-interest
        # sentence outright. Not a substitute for reading the file.
        assert hidden not in scenario["setting"], scenario["id"]
