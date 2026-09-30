from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from smalltobig.models.rule import RuleStatus
from smalltobig.seed import SeedFileError, load_seed
from smalltobig.store import db, repo_conflicts, repo_rules

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator

REAL_SEED = Path(__file__).resolve().parents[2] / "docs" / "seed" / "rules.yaml"
NOW = datetime(2026, 9, 29, tzinfo=UTC)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def test_loads_every_seed_rule_as_an_unverified_candidate(conn: sqlite3.Connection) -> None:
    summary = load_seed(conn, REAL_SEED, now=NOW)

    rules = repo_rules.list_all(conn)
    assert summary.rules_added == len(rules) == 15
    for rule in rules:
        assert rule.status == RuleStatus.CANDIDATE
        assert rule.claims == []
        assert rule.basis
        assert rule.cited_sources


def test_citations_are_readable_titles_not_raw_ids(conn: sqlite3.Connection) -> None:
    load_seed(conn, REAL_SEED, now=NOW)
    rule = repo_rules.get(conn, "ask-follow-up-questions")
    assert rule is not None
    assert any("It Doesn't Hurt to Ask" in citation for citation in rule.cited_sources)
    assert not any(citation.startswith("src_") for citation in rule.cited_sources)


def test_loads_the_disagreements_for_arbitration(conn: sqlite3.Connection) -> None:
    summary = load_seed(conn, REAL_SEED, now=NOW)
    assert summary.conflicts_added == 3
    conflict = repo_conflicts.get_by_pair(conn, "ask-follow-up-questions", "balance-the-airtime")
    assert conflict is not None
    assert conflict.status.value == "proposed"
    assert conflict.resolution is None


def test_running_twice_adds_nothing(conn: sqlite3.Connection) -> None:
    load_seed(conn, REAL_SEED, now=NOW)
    again = load_seed(conn, REAL_SEED, now=NOW)
    assert (again.rules_added, again.rules_skipped) == (0, 15)
    assert again.conflicts_added == 0


def test_running_again_never_overwrites_a_decision(conn: sqlite3.Connection) -> None:
    load_seed(conn, REAL_SEED, now=NOW)
    repo_rules.set_status(conn, "use-their-name", RuleStatus.REJECTED, decided_at=NOW)

    load_seed(conn, REAL_SEED, now=NOW)

    rule = repo_rules.get(conn, "use-their-name")
    assert rule is not None
    assert rule.status == RuleStatus.REJECTED


def test_a_seed_file_cannot_smuggle_in_an_accepted_or_verified_rule(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(
        """
rules:
  - id: sneaky
    name: Sneaky
    imperative: Do the thing.
    rationale: r
    when_to_apply: w
    antipattern: a
    evidence_tier: A
    status: accepted
    verified: true
    claims: [clm_1]
    sources: [some-source]
    basis: b
    rubric:
      - {id: x, check: "Did X?"}
""",
        encoding="utf-8",
    )
    load_seed(conn, path, now=NOW)

    rule = repo_rules.get(conn, "sneaky")
    assert rule is not None
    assert rule.status == RuleStatus.CANDIDATE
    assert rule.claims == []
    assert rule.cited_sources == ["some-source"]


def test_a_disagreement_naming_an_unknown_rule_is_skipped(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(
        """
rules: []
conflicts:
  - between: [ghost-a, ghost-b]
    note: n
    status: proposed
""",
        encoding="utf-8",
    )
    summary = load_seed(conn, path, now=NOW)
    assert (summary.conflicts_added, summary.conflicts_skipped) == (0, 1)


def test_missing_file_raises_a_clear_error(conn: sqlite3.Connection, tmp_path: Path) -> None:
    with pytest.raises(SeedFileError, match="not found"):
        load_seed(conn, tmp_path / "nope.yaml")
