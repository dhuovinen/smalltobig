"""Aggregate counts across the whole pipeline, for the home page."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3


@dataclass(frozen=True)
class HomeStats:
    sources: int
    claims: int
    rules_candidate: int
    rules_accepted: int
    conflicts_open: int
    drills: int
    sessions: int
    field_notes: int


def _count(conn: sqlite3.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0])


def home_stats(conn: sqlite3.Connection) -> HomeStats:
    return HomeStats(
        sources=_count(conn, "SELECT COUNT(*) FROM sources"),
        claims=_count(conn, "SELECT COUNT(*) FROM claims WHERE status = 'accepted'"),
        rules_candidate=_count(conn, "SELECT COUNT(*) FROM rules WHERE status = 'candidate'"),
        rules_accepted=_count(conn, "SELECT COUNT(*) FROM rules WHERE status = 'accepted'"),
        conflicts_open=_count(conn, "SELECT COUNT(*) FROM conflicts WHERE status = 'proposed'"),
        drills=_count(conn, "SELECT COUNT(*) FROM drills"),
        sessions=_count(conn, "SELECT COUNT(*) FROM sessions"),
        field_notes=_count(conn, "SELECT COUNT(*) FROM field_notes"),
    )
