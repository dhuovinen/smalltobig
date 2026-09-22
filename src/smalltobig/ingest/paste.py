"""Ingest paths 1 and 3 — paste raw text, or a URL plus text you supply.

Same code either way; a URL just gets recorded on the Source for provenance
(docs/DECISIONS.md #7 — no auto-fetcher, ever).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from smalltobig.ingest.normalize import normalize_plain_text
from smalltobig.models.source import Source, SourceKind, generate_source_id
from smalltobig.store import repo_sources

if TYPE_CHECKING:
    import sqlite3

    from smalltobig.config import Settings


class DuplicateSourceError(Exception):
    """Raised when the exact same bytes were already ingested as another source."""

    def __init__(self, existing: Source) -> None:
        super().__init__(f"identical content already ingested as {existing.id!r}")
        self.existing = existing


def ingest_pasted_text(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    text: str,
    title: str,
    kind: SourceKind,
    author: str | None = None,
    url: str | None = None,
    license_note: str | None = None,
) -> Source:
    raw_bytes = text.encode("utf-8")
    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    existing = repo_sources.get_by_sha256(conn, sha256)
    if existing is not None:
        raise DuplicateSourceError(existing)

    source = Source(
        id=generate_source_id(title, sha256),
        title=title,
        author=author,
        kind=kind,
        url=url,
        retrieved_at=datetime.now(UTC),
        sha256=sha256,
        license_note=license_note,
        original_filename=None,
    )

    dest_dir = settings.sources_dir / source.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "raw.txt").write_text(text, encoding="utf-8")
    (dest_dir / "normalized.txt").write_text(normalize_plain_text(text), encoding="utf-8")

    repo_sources.create(conn, source, raw_extension=".txt")
    return source
