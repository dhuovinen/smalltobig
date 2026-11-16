"""Load the starter rules and disagreements from docs/seed/ into the database.

The seed was drafted from abstracts and secondary summaries, not from primary
text run through the verify gate (see the header of docs/seed/rules.yaml). So
every rule is loaded as a *candidate* with no claims, whatever the file says,
and keeps `basis` and `cited_sources` so the UI can show that it is unverified
(CLAUDE.md non-negotiables #1 and #2). Nothing here can accept a rule.

Re-running is safe: an id already in the database is skipped, never
overwritten, so a decision you made survives.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from smalltobig.models.conflict import Conflict, ConflictStatus, generate_conflict_id
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.store import repo_conflicts, repo_rules

if TYPE_CHECKING:
    import sqlite3

    from smalltobig.config import Settings

RULES_FILENAME = "rules.yaml"
SOURCES_FILENAME = "sources.yaml"


class SeedFileError(Exception):
    pass


@dataclass(frozen=True)
class SeedSummary:
    rules_added: int
    rules_skipped: int
    conflicts_added: int
    conflicts_skipped: int


def default_seed_dir(settings: Settings) -> Path:
    """docs/seed next to the package (an editable install), else under repo_root."""
    beside_package = Path(__file__).resolve().parents[2] / "docs" / "seed"
    if (beside_package / RULES_FILENAME).exists():
        return beside_package
    return settings.repo_root / "docs" / "seed"


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SeedFileError(f"seed file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise SeedFileError(f"seed file is not valid YAML: {path}") from exc
    if not isinstance(data, dict):
        raise SeedFileError(f"seed file has no top-level mapping: {path}")
    return data


def _citation(source_id: str, sources: dict[str, dict[str, Any]]) -> str:
    source = sources.get(source_id)
    if source is None:
        return source_id
    parts = [str(source.get("title", source_id))]
    who = ", ".join(str(part) for part in (source.get("author"), source.get("year")) if part)
    return f"{parts[0]} — {who}" if who else parts[0]


def load_seed(
    conn: sqlite3.Connection, rules_file: Path, *, now: datetime | None = None
) -> SeedSummary:
    now = now or datetime.now(UTC)
    doc = _read_yaml(rules_file)

    sources_path = rules_file.with_name(SOURCES_FILENAME)
    sources: dict[str, dict[str, Any]] = {}
    if sources_path.exists():
        sources = {str(s["id"]): s for s in _read_yaml(sources_path).get("sources", [])}

    rules_added = rules_skipped = 0
    for raw in doc.get("rules", []):
        if repo_rules.get(conn, raw["id"]) is not None:
            rules_skipped += 1
            continue
        repo_rules.create(
            conn,
            Rule(
                id=raw["id"],
                name=raw["name"],
                imperative=raw["imperative"],
                rationale=" ".join(str(raw["rationale"]).split()),
                when_to_apply=raw["when_to_apply"],
                antipattern=raw["antipattern"],
                evidence_tier=raw["evidence_tier"],
                status=RuleStatus.CANDIDATE,
                claims=[],
                rubric=[RubricItem(**item) for item in raw["rubric"]],
                basis=" ".join(str(raw["basis"]).split()) if raw.get("basis") else None,
                cited_sources=[_citation(sid, sources) for sid in raw.get("sources", [])],
                created_at=now,
            ),
        )
        rules_added += 1

    conflicts_added = conflicts_skipped = 0
    for raw in doc.get("conflicts", []):
        between = list(raw["between"])
        if (
            len(between) != 2
            or any(repo_rules.get(conn, rule_id) is None for rule_id in between)
            or repo_conflicts.get_by_pair(conn, between[0], between[1]) is not None
        ):
            conflicts_skipped += 1
            continue
        proposed = raw.get("proposed_resolution")
        repo_conflicts.create(
            conn,
            Conflict(
                id=generate_conflict_id(between[0], between[1]),
                between=between,
                note=" ".join(str(raw["note"]).split()),
                status=ConflictStatus.PROPOSED,
                proposed_resolution=" ".join(str(proposed).split()) if proposed else None,
                created_at=now,
            ),
        )
        conflicts_added += 1

    return SeedSummary(rules_added, rules_skipped, conflicts_added, conflicts_skipped)
