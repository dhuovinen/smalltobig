from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from smalltobig.store import db, repo_rules

if TYPE_CHECKING:
    from pathlib import Path

OLD_RULES_TABLE = """
CREATE TABLE rules (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, imperative TEXT NOT NULL,
    rationale TEXT NOT NULL, when_to_apply TEXT NOT NULL, antipattern TEXT NOT NULL,
    evidence_tier TEXT NOT NULL, status TEXT NOT NULL, claims_json TEXT NOT NULL,
    rubric_json TEXT NOT NULL, prerequisites_json TEXT NOT NULL, superseded_by TEXT,
    created_at TEXT NOT NULL, decided_at TEXT
);
"""


def test_connecting_to_a_database_from_before_the_columns_existed_adds_them(
    tmp_path: Path,
) -> None:
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(OLD_RULES_TABLE)
    old.execute(
        "INSERT INTO rules VALUES ('r1','R','i','r','w','a','A','accepted','[]','[]','[]',"
        "NULL,'2026-09-22T00:00:00+00:00',NULL)"
    )
    old.commit()
    old.close()

    conn = db.connect(path)
    try:
        rule = repo_rules.get(conn, "r1")
    finally:
        conn.close()

    assert rule is not None
    assert rule.basis is None
    assert rule.cited_sources == []


def test_connecting_twice_is_harmless(tmp_path: Path) -> None:
    db.connect(tmp_path / "x.db").close()
    db.connect(tmp_path / "x.db").close()
