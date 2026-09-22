"""Reads and writes for the `claims` table — the row-to-model boundary."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from smalltobig.models.claim import Claim, ClaimStatus, ClaimType

if TYPE_CHECKING:
    import sqlite3


def create(conn: sqlite3.Connection, claim: Claim) -> None:
    conn.execute(
        """
        INSERT INTO claims
            (id, source_id, chunk_index, verbatim, paraphrase, claim_type,
             status, start, end, rejection_reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            claim.id,
            claim.source_id,
            claim.chunk_index,
            claim.verbatim,
            claim.paraphrase,
            claim.claim_type.value,
            claim.status.value,
            claim.start,
            claim.end,
            claim.rejection_reason,
            claim.created_at.isoformat(),
        ),
    )
    conn.commit()


def _row_to_claim(row: sqlite3.Row) -> Claim:
    return Claim(
        id=row["id"],
        source_id=row["source_id"],
        chunk_index=row["chunk_index"],
        verbatim=row["verbatim"],
        paraphrase=row["paraphrase"],
        claim_type=ClaimType(row["claim_type"]),
        status=ClaimStatus(row["status"]),
        start=row["start"],
        end=row["end"],
        rejection_reason=row["rejection_reason"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def list_by_source(conn: sqlite3.Connection, source_id: str) -> list[Claim]:
    rows = conn.execute(
        "SELECT * FROM claims WHERE source_id = ? ORDER BY chunk_index, id", (source_id,)
    ).fetchall()
    return [_row_to_claim(row) for row in rows]


def delete_by_source(conn: sqlite3.Connection, source_id: str) -> None:
    conn.execute("DELETE FROM claims WHERE source_id = ?", (source_id,))
    conn.commit()
