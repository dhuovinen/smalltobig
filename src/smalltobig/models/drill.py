"""Drill: one rule, one generated stimulus, one typed response, scored
against that rule's rubric only. See docs/PLAN.md §2 Stage 5.

Every rubric result that passes carries a quoted span from the response,
verified by the same byte-exact gate as claims (docs/PLAN.md §4 — "the
quote gets the same exact-match treatment as Stage 2"). A "passed" the
model didn't back with a real quote is downgraded to failed rather than
trusted — see practice/drills.py.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel


class RubricResult(BaseModel):
    rubric_id: str
    passed: bool
    quote: str | None = None


class Drill(BaseModel):
    id: str
    rule_id: str
    stimulus: str
    response: str
    rubric_results: list[RubricResult]
    success: bool
    created_at: datetime


def generate_drill_id(rule_id: str, stimulus: str, response: str) -> str:
    digest = hashlib.sha256(f"{rule_id}:{stimulus}:{response}".encode()).hexdigest()
    return f"drl_{digest[:8]}"
