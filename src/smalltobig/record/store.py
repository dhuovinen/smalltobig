"""The per-profile HTMSW store (DECISIONS #24).

One SQLite file per privacy profile, `settings.record_db_path`:

- Both profiles: `step_outcomes`, integers only (FR-51; tests/test_privacy.py
  asserts no TEXT column), plus `domain_refs`, which maps framework domain ids to
  integers. That is reference data from domains.yaml, never user text.
- `full` only: `sessions` and `verdicts`, which keep the transcript, debrief prose,
  consent, quotes and the model's request and reply. These tables are not even
  created in an `abstracted` store.

The file is created owner-only (0600). A `full` store is the most sensitive file the
app produces (DECISIONS #24) and lives under data_dir, outside the repository.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import TYPE_CHECKING, Literal

from smalltobig.record.models import Outcome
from smalltobig.record.projection import project

if TYPE_CHECKING:
    from pathlib import Path

    from smalltobig.framework.loader import Framework
    from smalltobig.record.models import SessionRecord

Profile = Literal["abstracted", "full"]
SOURCE_CODES = {"rehearsal": 1, "real": 2}
SOURCE_NAMES = {v: k for k, v in SOURCE_CODES.items()}

COMMON_SCHEMA = """
CREATE TABLE IF NOT EXISTS domain_refs (
    ref INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS step_outcomes (
    id INTEGER PRIMARY KEY,
    at INTEGER NOT NULL,
    step_order INTEGER NOT NULL,
    domain_ref INTEGER NOT NULL REFERENCES domain_refs(ref),
    source INTEGER NOT NULL CHECK (source IN (1, 2)),
    passed INTEGER NOT NULL CHECK (passed IN (0, 1))
);
CREATE TABLE IF NOT EXISTS store_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    profile_code INTEGER NOT NULL CHECK (profile_code IN (1, 2))
);
"""

FULL_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,
    domain_id TEXT NOT NULL,
    cluster_id TEXT,
    partner_id TEXT,
    consent TEXT NOT NULL,
    turns_json TEXT NOT NULL,
    account TEXT,
    model_messages_json TEXT NOT NULL,
    model_reply TEXT
);
CREATE TABLE IF NOT EXISTS verdicts (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL,
    rubric_id TEXT NOT NULL,
    passed INTEGER NOT NULL,
    quote TEXT,
    partner_quote TEXT,
    reason TEXT
);
"""

PROFILE_CODES: dict[Profile, int] = {"abstracted": 1, "full": 2}


class ProfileMismatchError(RuntimeError):
    """A store created under one profile was opened under the other."""


def connect(path: Path, profile: Profile) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        # Create owner-only before SQLite writes anything into it.
        os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(COMMON_SCHEMA)
    if profile == "full":
        conn.executescript(FULL_SCHEMA)
    row = conn.execute("SELECT profile_code FROM store_meta WHERE id = 1").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO store_meta (id, profile_code) VALUES (1, ?)", (PROFILE_CODES[profile],)
        )
        conn.commit()
    elif row[0] != PROFILE_CODES[profile]:
        conn.close()
        raise ProfileMismatchError(
            f"{path.name} was created under a different privacy profile; "
            "records never move between profiles (FR-59)"
        )
    return conn


def _domain_ref(conn: sqlite3.Connection, slug: str) -> int:
    conn.execute("INSERT OR IGNORE INTO domain_refs (slug) VALUES (?)", (slug,))
    row = conn.execute("SELECT ref FROM domain_refs WHERE slug = ?", (slug,)).fetchone()
    return int(row[0])


def write(
    conn: sqlite3.Connection, fw: Framework, record: SessionRecord, profile: Profile
) -> list[Outcome]:
    """Store a session. Under `abstracted`, only `project(record)` reaches disk."""
    outcomes = project(fw, record)
    with conn:
        for o in outcomes:
            conn.execute(
                "INSERT INTO step_outcomes (at, step_order, domain_ref, source, passed) "
                "VALUES (?, ?, ?, ?, ?)",
                (o.at, o.step_order, _domain_ref(conn, o.domain_id),
                 SOURCE_CODES[o.source], int(o.passed)),
            )
        if profile == "full":
            cur = conn.execute(
                "INSERT INTO sessions (created_at, source, domain_id, cluster_id, partner_id, "
                "consent, turns_json, account, model_messages_json, model_reply) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.created_at.isoformat(), record.source, record.domain_id,
                    record.cluster_id, record.partner_id, record.consent,
                    json.dumps([t.model_dump() for t in record.turns]),
                    record.account, json.dumps(list(record.model_messages)),
                    record.model_reply,
                ),
            )
            for v in record.verdicts:
                conn.execute(
                    "INSERT INTO verdicts (session_id, step_id, rubric_id, passed, quote, "
                    "partner_quote, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (cur.lastrowid, v.step_id, v.rubric_id, int(v.passed), v.quote,
                     v.partner_quote, v.reason),
                )
    return outcomes


def outcomes(conn: sqlite3.Connection) -> list[Outcome]:
    rows = conn.execute(
        "SELECT o.at, o.step_order, d.slug, o.source, o.passed FROM step_outcomes o "
        "JOIN domain_refs d ON d.ref = o.domain_ref ORDER BY o.id"
    ).fetchall()
    return [
        Outcome(at=r[0], step_order=r[1], domain_id=r[2], source=SOURCE_NAMES[r[3]],
                passed=bool(r[4]))
        for r in rows
    ]


def sessions(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    """Full-profile session list, newest first. Empty under `abstracted`."""
    has = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'"
    ).fetchone()
    if not has:
        return []
    return conn.execute(
        "SELECT id, created_at, source, domain_id, partner_id, consent FROM sessions "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def purge(path: Path) -> bool:
    """Delete the store file for one profile (FR-55). Returns whether one existed."""
    existed = path.exists()
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = path.with_name(path.name + suffix)
        if candidate.exists():
            candidate.unlink()
    return existed
