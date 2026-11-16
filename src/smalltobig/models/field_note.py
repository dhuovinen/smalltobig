"""Debrief + FieldNote: what actually happened in a real conversation.

See docs/PLAN.md §2 Stage 5 (pre-brief/debrief) and Stage 6 — a field note
is weighted 3.0 against a roleplay's 1.0 and a drill's 0.5
(docs/DECISIONS.md #6), because it is the only signal that touches a real
conversation rather than a simulator. Every FieldNote's quote is verified
against the debrief's own text by the same gate as claims, drills and
roleplay — see practice/debrief.py.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel


class Debrief(BaseModel):
    id: str
    text: str
    created_at: datetime


class FieldNote(BaseModel):
    id: str
    debrief_id: str
    rule_id: str
    quote: str
    success: bool
    created_at: datetime


def generate_debrief_id(text: str, created_at: datetime) -> str:
    digest = hashlib.sha256(f"{text}:{created_at.isoformat()}".encode()).hexdigest()
    return f"dbf_{digest[:8]}"


def generate_field_note_id(debrief_id: str, rule_id: str) -> str:
    digest = hashlib.sha256(f"{debrief_id}:{rule_id}".encode()).hexdigest()
    return f"fn_{digest[:8]}"
