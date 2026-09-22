"""Integrity checks for the seed corpus in docs/seed/.

These run in CI because the seed files are hand-edited YAML that the rest of the
design leans on: a dangling source id or a rule that quietly loses its
`verified: false` marker would not fail anything at import time, but would
undermine the provenance guarantees described in docs/PLAN.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

SEED = Path(__file__).resolve().parent.parent / "docs" / "seed"
VALID_TIERS = {"A", "B", "C", "D"}


def _load(name: str) -> dict[str, Any]:
    with (SEED / name).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def sources() -> list[dict[str, Any]]:
    return _load("sources.yaml")["sources"]


@pytest.fixture(scope="module")
def rules_doc() -> dict[str, Any]:
    return _load("rules.yaml")


def test_source_ids_are_unique(sources: list[dict[str, Any]]) -> None:
    ids = [s["id"] for s in sources]
    assert len(ids) == len(set(ids))


def test_rule_ids_are_unique(rules_doc: dict[str, Any]) -> None:
    ids = [r["id"] for r in rules_doc["rules"]]
    assert len(ids) == len(set(ids))


def test_every_rule_cites_a_known_source(
    rules_doc: dict[str, Any], sources: list[dict[str, Any]]
) -> None:
    known = {s["id"] for s in sources}
    for rule in rules_doc["rules"]:
        assert rule["sources"], f"{rule['id']} cites no source"
        dangling = set(rule["sources"]) - known
        assert not dangling, f"{rule['id']} cites unknown source(s): {sorted(dangling)}"


def test_conflicts_reference_known_rules(rules_doc: dict[str, Any]) -> None:
    known = {r["id"] for r in rules_doc["rules"]}
    for conflict in rules_doc["conflicts"]:
        dangling = set(conflict["between"]) - known
        assert not dangling, f"conflict references unknown rule(s): {sorted(dangling)}"


def test_evidence_tiers_are_valid(rules_doc: dict[str, Any]) -> None:
    for rule in rules_doc["rules"]:
        assert rule["evidence_tier"] in VALID_TIERS, rule["id"]


def test_seed_rules_are_unverified_candidates(rules_doc: dict[str, Any]) -> None:
    """Nothing in the seed may present as accepted or source-verified.

    The seed was derived from abstracts and secondary summaries, not from
    primary text run through the verify gate. Promoting a rule here rather than
    through ingestion would attribute unsourced advice to a named author.
    """
    for rule in rules_doc["rules"]:
        assert rule["status"] == "candidate", f"{rule['id']} is not a candidate"
        assert rule["verified"] is False, f"{rule['id']} claims to be verified"


def test_every_rule_has_a_checkable_rubric(rules_doc: dict[str, Any]) -> None:
    for rule in rules_doc["rules"]:
        rubric = rule.get("rubric")
        assert rubric, f"{rule['id']} has no rubric"
        for item in rubric:
            assert item["id"] and item["check"]
            assert item["check"].rstrip().endswith("?"), (
                f"{rule['id']}/{item['id']} is not phrased as a yes/no question; "
                "rubric items must be boolean (docs/DECISIONS.md #5)"
            )


def test_sources_are_marked_not_ingested(sources: list[dict[str, Any]]) -> None:
    """No source can claim ingestion until there is an ingest pipeline to do it."""
    for source in sources:
        assert source["ingest_status"] == "not_ingested", source["id"]
