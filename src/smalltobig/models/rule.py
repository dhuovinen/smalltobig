"""Rule: candidate → you accept/reject/supersede → accepted.

See docs/PLAN.md §2 Stage 3. Evidence tiers are A-D, assigned from the
kind of evidence behind the claims, not how confidently they read —
docs/PLAN.md §4. Rubric items are boolean plus a quoted span, never a
1-10 scale (docs/DECISIONS.md #5); nothing here enforces that at the type
level beyond requiring `check` to be a question — the model is prompted
for it and a human reviews the result.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from smalltobig.models.source import slugify

EvidenceTier = Literal["A", "B", "C", "D"]


class RuleStatus(StrEnum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class RubricItem(BaseModel):
    id: str
    check: str


class Rule(BaseModel):
    id: str
    name: str
    imperative: str
    rationale: str
    when_to_apply: str
    antipattern: str
    evidence_tier: EvidenceTier
    status: RuleStatus
    claims: list[str]
    rubric: list[RubricItem]
    prerequisites: list[str] = []
    superseded_by: str | None = None
    # Starter rules (seed.py) have no claims: `basis` and `cited_sources` record
    # what they were drafted from, so a rule with `claims == []` can never pass
    # for source-verified. Synthesized rules leave both empty.
    basis: str | None = None
    cited_sources: list[str] = []
    created_at: datetime
    decided_at: datetime | None = None


def generate_rule_id(name: str) -> str:
    return slugify(name, max_words=6)
