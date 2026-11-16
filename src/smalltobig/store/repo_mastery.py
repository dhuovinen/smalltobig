"""Reads and writes for the `mastery` table — one row per rule."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from smalltobig.models.mastery import MIN_BOX, Mastery

if TYPE_CHECKING:
    import sqlite3


def get(conn: sqlite3.Connection, rule_id: str) -> Mastery | None:
    row = conn.execute("SELECT * FROM mastery WHERE rule_id = ?", (rule_id,)).fetchone()
    return _row_to_mastery(row) if row else None


def get_or_default(conn: sqlite3.Connection, rule_id: str, *, now: datetime) -> Mastery:
    existing = get(conn, rule_id)
    if existing is not None:
        return existing
    return Mastery(
        rule_id=rule_id, box=MIN_BOX, score=0.0, has_non_drill_evidence=False, updated_at=now
    )


def _row_to_mastery(row: sqlite3.Row) -> Mastery:
    return Mastery(
        rule_id=row["rule_id"],
        box=row["box"],
        score=row["score"],
        has_non_drill_evidence=bool(row["has_non_drill_evidence"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def upsert(conn: sqlite3.Connection, mastery: Mastery) -> None:
    conn.execute(
        """
        INSERT INTO mastery (rule_id, box, score, has_non_drill_evidence, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(rule_id) DO UPDATE SET
            box = excluded.box,
            score = excluded.score,
            has_non_drill_evidence = excluded.has_non_drill_evidence,
            updated_at = excluded.updated_at
        """,
        (
            mastery.rule_id,
            mastery.box,
            mastery.score,
            int(mastery.has_non_drill_evidence),
            mastery.updated_at.isoformat(),
        ),
    )
    conn.commit()


def list_all(conn: sqlite3.Connection) -> list[Mastery]:
    rows = conn.execute("SELECT * FROM mastery ORDER BY score ASC, rule_id").fetchall()
    return [_row_to_mastery(row) for row in rows]
