"""Ingest path 2 — the watched inbox folder.

Files dropped in settings.inbox_dir get picked up, moved to
settings.sources_dir/<id>/, and their original filename is recorded — see
docs/PLAN.md §2 Stage 1. Run by `stb ingest` (a poller can call the same
`poll_inbox` on a timer; none is wired up yet).
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from smalltobig.ingest.extract_text import SUPPORTED_SUFFIXES, extract_and_normalize
from smalltobig.models.source import Source, SourceKind, generate_source_id
from smalltobig.store import repo_sources

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

    from smalltobig.config import Settings


def scan_inbox(settings: Settings) -> list[Path]:
    if not settings.inbox_dir.is_dir():
        return []
    return sorted(
        p
        for p in settings.inbox_dir.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in SUPPORTED_SUFFIXES
    )


def _quarantine_duplicate(settings: Settings, path: Path) -> None:
    """Move a file whose content is already ingested out of the inbox, so
    it isn't reprocessed on every poll — without creating a second record."""
    duplicates_dir = settings.sources_dir / "_duplicates"
    duplicates_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), duplicates_dir / path.name)


def ingest_inbox_file(conn: sqlite3.Connection, settings: Settings, path: Path) -> Source | None:
    """Ingest one file already sitting in the inbox. Returns None (and
    quarantines the file) if its content duplicates an existing source."""
    raw_bytes = path.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    if repo_sources.get_by_sha256(conn, sha256) is not None:
        _quarantine_duplicate(settings, path)
        return None

    normalized = extract_and_normalize(path)
    suffix = path.suffix.lower()

    source = Source(
        id=generate_source_id(path.stem, sha256),
        title=path.stem,
        kind=SourceKind.NOTES,
        retrieved_at=datetime.now(UTC),
        sha256=sha256,
        original_filename=path.name,
    )

    dest_dir = settings.sources_dir / source.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), dest_dir / f"raw{suffix}")
    (dest_dir / "normalized.txt").write_text(normalized, encoding="utf-8")

    repo_sources.create(conn, source, raw_extension=suffix)
    return source


def poll_inbox(conn: sqlite3.Connection, settings: Settings) -> list[Source]:
    """Ingest every file currently in the inbox."""
    ingested = []
    for path in scan_inbox(settings):
        source = ingest_inbox_file(conn, settings, path)
        if source is not None:
            ingested.append(source)
    return ingested
