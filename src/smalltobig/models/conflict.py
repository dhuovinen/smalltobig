"""Conflict: two rules whose imperatives may not coexist, surfaced for you
to arbitrate. See docs/PLAN.md §2 Stage 3 — "that conflict log is,
plausibly, the most valuable artifact the app produces." The model
proposes; `resolution` is only ever written by a human (docs/DECISIONS.md
non-negotiable #2).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ConflictStatus(StrEnum):
    PROPOSED = "proposed"
    RESOLVED = "resolved"


class Conflict(BaseModel):
    id: str
    between: list[str]
    note: str
    status: ConflictStatus
    proposed_resolution: str | None = None
    resolution: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


def generate_conflict_id(rule_id_a: str, rule_id_b: str) -> str:
    pair = "|".join(sorted((rule_id_a, rule_id_b)))
    digest = hashlib.sha256(pair.encode()).hexdigest()
    return f"cfl_{digest[:8]}"
