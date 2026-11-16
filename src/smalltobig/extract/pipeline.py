"""Chunk -> LLM extraction -> verify gate -> persist.

Re-running extraction on a source replaces its prior claims, so the
rejection rate stays a clean regression metric across prompt changes
(docs/PLAN.md §5 Phase 2), rather than accumulating duplicates. The old
claims are only deleted once every chunk has been processed: the model can
drop out partway through, and that must not leave a source with none.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from smalltobig.extract.chunker import chunk_text
from smalltobig.extract.claims import extract_claims_from_chunk
from smalltobig.extract.verify import verify_claim
from smalltobig.models.claim import Claim, ClaimStatus, generate_claim_id
from smalltobig.store import repo_claims, repo_sources

if TYPE_CHECKING:
    import sqlite3

    from smalltobig.config import Settings
    from smalltobig.llm.client import LlmClient


@dataclass(frozen=True)
class ExtractionSummary:
    source_id: str
    chunks: int
    proposed: int
    accepted: int
    rejected: int

    @property
    def rejection_rate(self) -> float:
        return self.rejected / self.proposed if self.proposed else 0.0


class UnknownSourceError(Exception):
    def __init__(self, source_id: str) -> None:
        super().__init__(f"unknown source {source_id!r}")


def extract_source(
    conn: sqlite3.Connection,
    settings: Settings,
    client: LlmClient,
    source_id: str,
) -> ExtractionSummary:
    source = repo_sources.get(conn, source_id)
    if source is None:
        raise UnknownSourceError(source_id)

    normalized = repo_sources.normalized_path(settings, source_id).read_text(encoding="utf-8")
    chunks = chunk_text(normalized)

    new_claims: list[Claim] = []
    proposed = accepted = rejected = 0
    for chunk in chunks:
        for extracted in extract_claims_from_chunk(client, chunk.text):
            proposed += 1
            result = verify_claim(normalized, extracted.verbatim)
            claim = Claim(
                id=generate_claim_id(source_id, chunk.index, extracted.verbatim),
                source_id=source_id,
                chunk_index=chunk.index,
                verbatim=extracted.verbatim,
                paraphrase=extracted.paraphrase,
                claim_type=extracted.claim_type,
                status=ClaimStatus.ACCEPTED if result.accepted else ClaimStatus.REJECTED,
                start=result.start,
                end=result.end,
                rejection_reason=result.reason,
                created_at=datetime.now(UTC),
            )
            new_claims.append(claim)
            if result.accepted:
                accepted += 1
            else:
                rejected += 1

    repo_claims.delete_by_source(conn, source_id)
    for claim in new_claims:
        repo_claims.create(conn, claim)

    return ExtractionSummary(
        source_id=source_id,
        chunks=len(chunks),
        proposed=proposed,
        accepted=accepted,
        rejected=rejected,
    )
