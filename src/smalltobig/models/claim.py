"""Claim: verbatim span + paraphrase. See docs/PLAN.md §2 Stage 2.

A claim only carries (start, end) once it has survived the verify gate —
docs/DECISIONS.md #3. A rejected claim is kept, with its reason, so the
rejection rate stays measurable as an extraction-prompt regression metric.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ClaimType(StrEnum):
    PRESCRIPTIVE = "prescriptive"
    DESCRIPTIVE = "descriptive"
    EMPIRICAL_FINDING = "empirical_finding"
    ANECDOTE = "anecdote"


class ClaimStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Claim(BaseModel):
    id: str
    source_id: str
    chunk_index: int
    verbatim: str
    paraphrase: str
    claim_type: ClaimType
    status: ClaimStatus
    start: int | None = None
    end: int | None = None
    rejection_reason: str | None = None
    created_at: datetime


def generate_claim_id(source_id: str, chunk_index: int, verbatim: str) -> str:
    digest = hashlib.sha256(f"{source_id}:{chunk_index}:{verbatim}".encode()).hexdigest()
    return f"clm_{digest[:8]}"
