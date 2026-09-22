"""Scenarios are hand-authored YAML in settings.scenarios_dir, read-only
from the app's side — no SQLite table, and the app never writes one (see
scenarios/*.yaml at the repo root, and store/repo_lessons.py for the
same "read straight off disk" pattern applied to generated content).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from smalltobig.models.scenario import Persona, Scenario

if TYPE_CHECKING:
    from pathlib import Path

    from smalltobig.config import Settings


def get(settings: Settings, scenario_id: str) -> Scenario | None:
    path = settings.scenarios_dir / f"{scenario_id}.yaml"
    if not path.is_file():
        return None
    return _load(path)


def list_all(settings: Settings) -> list[Scenario]:
    if not settings.scenarios_dir.is_dir():
        return []
    scenarios = [_load(path) for path in sorted(settings.scenarios_dir.glob("*.yaml"))]
    return sorted(scenarios, key=lambda scenario: scenario.id)


def _load(path: Path) -> Scenario:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Scenario(
        id=data["id"],
        name=data["name"],
        setting=data["setting"],
        persona=Persona(**data["persona"]),
    )
