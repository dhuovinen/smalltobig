"""Reads and writes for the `debriefs` table — the raw free-text log."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from smalltobig.models.field_note import Debrief

if TYPE_CHECKING:
    import sqlite3


def create(conn: sqlite3.Connection, debrief: Debrief) -> None:
    conn.execute(
        "INSERT INTO debriefs (id, text, created_at) VALUES (?, ?, ?)",
        (debrief.id, debrief.text, debrief.created_at.isoformat()),
    )
    conn.commit()


def get(conn: sqlite3.Connection, debrief_id: str) -> Debrief | None:
    row = conn.execute("SELECT * FROM debriefs WHERE id = ?", (debrief_id,)).fetchone()
    if row is None:
        return None
    return Debrief(
        id=row["id"], text=row["text"], created_at=datetime.fromisoformat(row["created_at"])
    )
