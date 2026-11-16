"""Reads and writes for the `rules` table — the row-to-model boundary.

Status transitions (accept/reject/supersede) are a human decision
(docs/DECISIONS.md non-negotiable #2) — this module only persists them;
see synth/pipeline.py for why re-running synthesis never touches a rule
once it has left `candidate`.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from smalltobig.models.rule import RubricItem, Rule, RuleStatus

if TYPE_CHECKING:
    import sqlite3


def create(conn: sqlite3.Connection, rule: Rule) -> None:
    conn.execute(
        """
        INSERT INTO rules
            (id, name, imperative, rationale, when_to_apply, antipattern,
             evidence_tier, status, claims_json, rubric_json,
             prerequisites_json, superseded_by, created_at, decided_at,
             basis, cited_sources_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rule.id,
            rule.name,
            rule.imperative,
            rule.rationale,
            rule.when_to_apply,
            rule.antipattern,
            rule.evidence_tier,
            rule.status.value,
            json.dumps(rule.claims),
            json.dumps([item.model_dump() for item in rule.rubric]),
            json.dumps(rule.prerequisites),
            rule.superseded_by,
            rule.created_at.isoformat(),
            rule.decided_at.isoformat() if rule.decided_at else None,
            rule.basis,
            json.dumps(rule.cited_sources),
        ),
    )
    conn.commit()


def _row_to_rule(row: sqlite3.Row) -> Rule:
    return Rule(
        id=row["id"],
        name=row["name"],
        imperative=row["imperative"],
        rationale=row["rationale"],
        when_to_apply=row["when_to_apply"],
        antipattern=row["antipattern"],
        evidence_tier=row["evidence_tier"],
        status=RuleStatus(row["status"]),
        claims=json.loads(row["claims_json"]),
        rubric=[RubricItem(**item) for item in json.loads(row["rubric_json"])],
        prerequisites=json.loads(row["prerequisites_json"]),
        superseded_by=row["superseded_by"],
        created_at=datetime.fromisoformat(row["created_at"]),
        decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
        basis=row["basis"],
        cited_sources=json.loads(row["cited_sources_json"]),
    )


def get(conn: sqlite3.Connection, rule_id: str) -> Rule | None:
    row = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
    return _row_to_rule(row) if row else None


def list_all(conn: sqlite3.Connection) -> list[Rule]:
    rows = conn.execute("SELECT * FROM rules ORDER BY evidence_tier, id").fetchall()
    return [_row_to_rule(row) for row in rows]


def find_by_claim_set(conn: sqlite3.Connection, claim_ids: set[str]) -> Rule | None:
    """A rule already covering exactly this set of claims, regardless of
    status — used so re-running synthesis never proposes a duplicate for a
    cluster it has already drafted a rule from."""
    for rule in list_all(conn):
        if set(rule.claims) == claim_ids:
            return rule
    return None


def set_status(
    conn: sqlite3.Connection,
    rule_id: str,
    status: RuleStatus,
    *,
    decided_at: datetime,
    superseded_by: str | None = None,
) -> None:
    conn.execute(
        "UPDATE rules SET status = ?, decided_at = ?, superseded_by = ? WHERE id = ?",
        (status.value, decided_at.isoformat(), superseded_by, rule_id),
    )
    conn.commit()
