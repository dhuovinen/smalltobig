"""Reads and writes for the `sources` table — the row-to-model boundary."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from smalltobig.models.source import Source, SourceKind

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

    from smalltobig.config import Settings


def create(conn: sqlite3.Connection, source: Source, *, raw_extension: str) -> None:
    conn.execute(
        """
        INSERT INTO sources
            (id, title, author, kind, url, retrieved_at, sha256,
             license_note, original_filename, raw_extension)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source.id,
            source.title,
            source.author,
            source.kind.value,
            source.url,
            source.retrieved_at.isoformat(),
            source.sha256,
            source.license_note,
            source.original_filename,
            raw_extension,
        ),
    )
    conn.commit()


def _row_to_source(row: sqlite3.Row) -> Source:
    return Source(
        id=row["id"],
        title=row["title"],
        author=row["author"],
        kind=SourceKind(row["kind"]),
        url=row["url"],
        retrieved_at=datetime.fromisoformat(row["retrieved_at"]),
        sha256=row["sha256"],
        license_note=row["license_note"],
        original_filename=row["original_filename"],
    )


def get(conn: sqlite3.Connection, source_id: str) -> Source | None:
    row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    return _row_to_source(row) if row else None


def get_by_sha256(conn: sqlite3.Connection, sha256: str) -> Source | None:
    row = conn.execute("SELECT * FROM sources WHERE sha256 = ?", (sha256,)).fetchone()
    return _row_to_source(row) if row else None


def get_raw_extension(conn: sqlite3.Connection, source_id: str) -> str | None:
    row = conn.execute(
        "SELECT raw_extension FROM sources WHERE id = ?", (source_id,)
    ).fetchone()
    return row["raw_extension"] if row else None


def list_all(conn: sqlite3.Connection) -> list[Source]:
    rows = conn.execute("SELECT * FROM sources ORDER BY retrieved_at DESC").fetchall()
    return [_row_to_source(row) for row in rows]


def raw_path(settings: Settings, source_id: str, raw_extension: str) -> Path:
    return settings.sources_dir / source_id / f"raw{raw_extension}"


def normalized_path(settings: Settings, source_id: str) -> Path:
    return settings.sources_dir / source_id / "normalized.txt"
