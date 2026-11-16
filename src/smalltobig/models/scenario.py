"""Scenario + Persona: hand-authored seed content, not generated or
workflow-tracked. See docs/PLAN.md §2 Stage 5.

`Persona.private_instructions` and `hidden_interest` are fed to the
roleplay actor only (practice/roleplay.py) — the judge never sees them
(docs/DECISIONS.md non-negotiable #4), and neither is ever shown to the
practicer while the session is live.
"""

from __future__ import annotations

from pydantic import BaseModel


class Persona(BaseModel):
    name: str
    warmth: str
    verbosity: str
    hidden_interest: str
    private_instructions: str


class Scenario(BaseModel):
    id: str
    name: str
    setting: str
    persona: Persona
