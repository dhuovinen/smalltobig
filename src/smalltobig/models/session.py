"""Session: a finished roleplay transcript, scored against the target
lesson's rules. See docs/PLAN.md §2 Stage 5.

`rubric_results` covers every rule in `rule_ids` combined; each item's
quote is verified against the practicer's own turns by the same gate as
Stage 2 (see practice/judge.py) — never trust the model's yes without a
span that actually appears in what was typed.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Turn(BaseModel):
    speaker: Literal["user", "partner"]
    text: str


class SessionRubricResult(BaseModel):
    rule_id: str
    rubric_id: str
    passed: bool
    quote: str | None = None


class Session(BaseModel):
    id: str
    lesson_id: str
    scenario_id: str
    rule_ids: list[str]
    turns: list[Turn]
    rubric_results: list[SessionRubricResult]
    created_at: datetime
    ended_at: datetime


def generate_session_id(lesson_id: str, scenario_id: str, created_at: datetime) -> str:
    key = f"{lesson_id}:{scenario_id}:{created_at.isoformat()}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return f"ses_{digest[:8]}"
