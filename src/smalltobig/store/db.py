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
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
