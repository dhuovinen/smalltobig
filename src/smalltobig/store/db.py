"""SQLite connection and schema.

Records only — the source bytes themselves live on disk under
settings.sources_dir (docs/PLAN.md §2 Stage 1), keyed by the same id.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    kind TEXT NOT NULL,
    url TEXT,
    retrieved_at TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    license_note TEXT,
    original_filename TEXT,
    raw_extension TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id),
    chunk_index INTEGER NOT NULL,
    verbatim TEXT NOT NULL,
    paraphrase TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    status TEXT NOT NULL,
    start INTEGER,
    end INTEGER,
    rejection_reason TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_claims_source_id ON claims(source_id);

CREATE TABLE IF NOT EXISTS rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    imperative TEXT NOT NULL,
    rationale TEXT NOT NULL,
    when_to_apply TEXT NOT NULL,
    antipattern TEXT NOT NULL,
    evidence_tier TEXT NOT NULL,
    status TEXT NOT NULL,
    claims_json TEXT NOT NULL,
    rubric_json TEXT NOT NULL,
    prerequisites_json TEXT NOT NULL,
    superseded_by TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS conflicts (
    id TEXT PRIMARY KEY,
    between_json TEXT NOT NULL,
    note TEXT NOT NULL,
    status TEXT NOT NULL,
    proposed_resolution TEXT,
    resolution TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS drills (
    id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL REFERENCES rules(id),
    stimulus TEXT NOT NULL,
    response TEXT NOT NULL,
    rubric_results_json TEXT NOT NULL,
    success INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_drills_rule_id ON drills(rule_id);

CREATE TABLE IF NOT EXISTS mastery (
    rule_id TEXT PRIMARY KEY REFERENCES rules(id),
    box INTEGER NOT NULL,
    score REAL NOT NULL,
    has_non_drill_evidence INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
