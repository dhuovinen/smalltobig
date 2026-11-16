"""The standing self-profile: intake flags only (FR-21, FR-24).

One row. The stored JSON holds question ids mapped to option ids from
framework/personas.yaml, validated by `normalize()` before every write, so no
name, age, employer or condition can be stored here even by accident.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from smalltobig.intake.classify import normalize

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Mapping

    from smalltobig.framework.loader import Framework


def load(conn: sqlite3.Connection) -> dict[str, str]:
    row = conn.execute("SELECT answers_json FROM self_profile WHERE id = 1").fetchone()
    if row is None:
        return {}
    data = json.loads(row[0])
    assert isinstance(data, dict)
    return {str(k): str(v) for k, v in data.items()}


def save(
    conn: sqlite3.Connection, fw: Framework, answers: Mapping[str, str | None]
) -> dict[str, str]:
    """Validate and store. Returns what was stored. Raises IntakeError on bad input."""
    cleaned = normalize(fw, answers)
    conn.execute(
        """
        INSERT INTO self_profile (id, answers_json, updated_at) VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            answers_json = excluded.answers_json,
            updated_at = excluded.updated_at
        """,
        (json.dumps(cleaned, sort_keys=True), datetime.now(UTC).isoformat()),
    )
    conn.commit()
    return cleaned


def clear(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM self_profile")
    conn.commit()
