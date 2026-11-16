"""HTMSW rehearsal: talk to a partner from framework/partners.yaml.

The actor is the shared one in practice/roleplay.py. It builds its prompt from a
Scenario (setting plus persona) and the transcript, and has no knowledge of
rubrics, steps or the framework (FR-42). This module adapts a Partner into that
Scenario shape and cleans stage directions out of replies (DECISIONS #25).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from smalltobig.models.scenario import Persona, Scenario
from smalltobig.models.session import Turn
from smalltobig.practice.roleplay import generate_reply

if TYPE_CHECKING:
    from smalltobig.framework.loader import Framework, Partner
    from smalltobig.llm.client import LlmClient


def as_scenario(partner: Partner) -> Scenario:
    return Scenario(
        id=f"htmsw-{partner.id}",
        name=partner.name,
        setting=partner.setting,
        persona=Persona(
            name=partner.name,
            warmth=partner.warmth,
            verbosity=partner.verbosity,
            hidden_interest=partner.hidden_interest,
            private_instructions=partner.private_instructions,
        ),
    )


def partners_for(fw: Framework, domain_id: str) -> list[Partner]:
    return [p for p in fw.partners if domain_id in p.domains]


def opening(partner: Partner) -> list[Turn]:
    """The fixed first line, so a rehearsal starts the same way every time."""
    return [Turn(speaker="partner", text=partner.opening_line.strip())]


_WRAPPED = re.compile(r"\*([^*\n]{1,200})\*|\[([^\]\n]{1,200})\]|\(([^)\n]{1,200})\)")


def _drop_directions(match: re.Match[str]) -> str:
    inner = next(g for g in match.groups() if g is not None)
    if match.group(0).startswith("*") and " " not in inner.strip():
        return inner  # single-word *emphasis*: keep the word
    if match.group(0).startswith("(") and " " not in inner.strip():
        return match.group(0)  # a one-word aside like "(sorry)" is speech
    return ""  # a multi-word *stage direction* or [aside]


def clean(line: str) -> str:
    """Drop stage directions the actor adds despite being told not to.

    Live runs with an 8B model produced lines like "*leans slightly forward*".
    Multi-word spans in asterisks, brackets or parentheses are removed; single-word
    *emphasis* keeps its word. If cleaning would leave nothing, the line is kept.
    """
    without = _WRAPPED.sub(_drop_directions, line)
    return re.sub(r"\s+", " ", without).strip() or line.strip()


def reply(client: LlmClient, partner: Partner, turns: list[Turn]) -> str:
    return clean(generate_reply(client, as_scenario(partner), turns))
