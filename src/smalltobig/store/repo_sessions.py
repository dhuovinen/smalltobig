"""Reads and writes for the `sessions` table — an append-only roleplay log."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from smalltobig.models.session import Session, SessionRubricResult, Turn

if TYPE_CHECKING:
    import sqlite3


def create(conn: sqlite3.Connection, session: Session) -> None:
    conn.execute(
        """
        INSERT INTO sessions
            (id, lesson_id, scenario_id, rule_ids_json, turns_json,
             rubric_results_json, created_at, ended_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session.id,
            session.lesson_id,
            session.scenario_id,
            json.dumps(session.rule_ids),
            json.dumps([turn.model_dump() for turn in session.turns]),
            json.dumps([result.model_dump() for result in session.rubric_results]),
            session.created_at.isoformat(),
            session.ended_at.isoformat(),
        ),
    )
    conn.commit()


def _row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        lesson_id=row["lesson_id"],
        scenario_id=row["scenario_id"],
        rule_ids=json.loads(row["rule_ids_json"]),
        turns=[Turn(**turn) for turn in json.loads(row["turns_json"])],
        rubric_results=[
            SessionRubricResult(**result) for result in json.loads(row["rubric_results_json"])
        ],
        created_at=datetime.fromisoformat(row["created_at"]),
        ended_at=datetime.fromisoformat(row["ended_at"]),
    )


def get(conn: sqlite3.Connection, session_id: str) -> Session | None:
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return _row_to_session(row) if row else None


def list_by_lesson(conn: sqlite3.Connection, lesson_id: str) -> list[Session]:
    rows = conn.execute(
        "SELECT * FROM sessions WHERE lesson_id = ? ORDER BY created_at DESC", (lesson_id,)
    ).fetchall()
    return [_row_to_session(row) for row in rows]


def list_all(conn: sqlite3.Connection) -> list[Session]:
    rows = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
    return [_row_to_session(row) for row in rows]
