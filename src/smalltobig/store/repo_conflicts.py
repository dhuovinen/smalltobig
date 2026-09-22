"""Reads and writes for the `conflicts` table.

`resolution` is only ever set by resolve() — a human writing the actual
call, distinct from the model's `proposed_resolution` (docs/DECISIONS.md
non-negotiable #2).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from smalltobig.models.conflict import Conflict, ConflictStatus

if TYPE_CHECKING:
    import sqlite3


def create(conn: sqlite3.Connection, conflict: Conflict) -> None:
    conn.execute(
        """
        INSERT INTO conflicts
            (id, between_json, note, status, proposed_resolution,
             resolution, created_at, resolved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            conflict.id,
            json.dumps(conflict.between),
            conflict.note,
            conflict.status.value,
            conflict.proposed_resolution,
            conflict.resolution,
            conflict.created_at.isoformat(),
            conflict.resolved_at.isoformat() if conflict.resolved_at else None,
        ),
    )
    conn.commit()


def _row_to_conflict(row: sqlite3.Row) -> Conflict:
    return Conflict(
        id=row["id"],
        between=json.loads(row["between_json"]),
        note=row["note"],
        status=ConflictStatus(row["status"]),
        proposed_resolution=row["proposed_resolution"],
        resolution=row["resolution"],
        created_at=datetime.fromisoformat(row["created_at"]),
        resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
    )


def get(conn: sqlite3.Connection, conflict_id: str) -> Conflict | None:
    row = conn.execute("SELECT * FROM conflicts WHERE id = ?", (conflict_id,)).fetchone()
    return _row_to_conflict(row) if row else None


def list_all(conn: sqlite3.Connection) -> list[Conflict]:
    rows = conn.execute("SELECT * FROM conflicts ORDER BY status, id").fetchall()
    return [_row_to_conflict(row) for row in rows]


def get_by_pair(conn: sqlite3.Connection, rule_id_a: str, rule_id_b: str) -> Conflict | None:
    """A conflict already recorded for this unordered pair, in any status —
    re-running conflict detection must never duplicate or silently
    overwrite a human's resolution."""
    pair = {rule_id_a, rule_id_b}
    for conflict in list_all(conn):
        if set(conflict.between) == pair:
            return conflict
    return None


def resolve(
    conn: sqlite3.Connection, conflict_id: str, resolution: str, *, resolved_at: datetime
) -> None:
    conn.execute(
        "UPDATE conflicts SET status = ?, resolution = ?, resolved_at = ? WHERE id = ?",
        (ConflictStatus.RESOLVED.value, resolution, resolved_at.isoformat(), conflict_id),
    )
    conn.commit()
