"""Reads and writes for the `field_notes` table — an append-only log,
the only mastery signal weighted 3.0 (docs/PLAN.md §2 Stage 6).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from smalltobig.models.field_note import FieldNote

if TYPE_CHECKING:
    import sqlite3


def create(conn: sqlite3.Connection, field_note: FieldNote) -> None:
    conn.execute(
        """
        INSERT INTO field_notes (id, debrief_id, rule_id, quote, success, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            field_note.id,
            field_note.debrief_id,
            field_note.rule_id,
            field_note.quote,
            int(field_note.success),
            field_note.created_at.isoformat(),
        ),
    )
    conn.commit()


def _row_to_field_note(row: sqlite3.Row) -> FieldNote:
    return FieldNote(
        id=row["id"],
        debrief_id=row["debrief_id"],
        rule_id=row["rule_id"],
        quote=row["quote"],
        success=bool(row["success"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def list_by_rule(conn: sqlite3.Connection, rule_id: str) -> list[FieldNote]:
    rows = conn.execute(
        "SELECT * FROM field_notes WHERE rule_id = ? ORDER BY created_at DESC", (rule_id,)
    ).fetchall()
    return [_row_to_field_note(row) for row in rows]


def list_by_debrief(conn: sqlite3.Connection, debrief_id: str) -> list[FieldNote]:
    rows = conn.execute(
        "SELECT * FROM field_notes WHERE debrief_id = ? ORDER BY id", (debrief_id,)
    ).fetchall()
    return [_row_to_field_note(row) for row in rows]


def list_all(conn: sqlite3.Connection) -> list[FieldNote]:
    rows = conn.execute("SELECT * FROM field_notes ORDER BY created_at DESC").fetchall()
    return [_row_to_field_note(row) for row in rows]
