"""Reads and writes for the `drills` table — an append-only practice log."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from smalltobig.models.drill import Drill, RubricResult

if TYPE_CHECKING:
    import sqlite3


def create(conn: sqlite3.Connection, drill: Drill) -> None:
    conn.execute(
        """
        INSERT INTO drills
            (id, rule_id, stimulus, response, rubric_results_json, success, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            drill.id,
            drill.rule_id,
            drill.stimulus,
            drill.response,
            json.dumps([result.model_dump() for result in drill.rubric_results]),
            int(drill.success),
            drill.created_at.isoformat(),
        ),
    )
    conn.commit()


def _row_to_drill(row: sqlite3.Row) -> Drill:
    return Drill(
        id=row["id"],
        rule_id=row["rule_id"],
        stimulus=row["stimulus"],
        response=row["response"],
        rubric_results=[RubricResult(**item) for item in json.loads(row["rubric_results_json"])],
        success=bool(row["success"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def get(conn: sqlite3.Connection, drill_id: str) -> Drill | None:
    row = conn.execute("SELECT * FROM drills WHERE id = ?", (drill_id,)).fetchone()
    return _row_to_drill(row) if row else None


def list_by_rule(conn: sqlite3.Connection, rule_id: str) -> list[Drill]:
    rows = conn.execute(
        "SELECT * FROM drills WHERE rule_id = ? ORDER BY created_at DESC", (rule_id,)
    ).fetchall()
    return [_row_to_drill(row) for row in rows]
