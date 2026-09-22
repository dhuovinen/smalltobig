"""Order accepted rules for lesson sequencing, and name a group of them.

See docs/PLAN.md §2 Stage 4: "Ordering comes from the prerequisite DAG,
then evidence tier, then your weakest mastery scores."
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from smalltobig.llm.json_extract import extract_json_object

if TYPE_CHECKING:
    from smalltobig.llm.client import LlmClient
    from smalltobig.models.mastery import Mastery
    from smalltobig.models.rule import Rule

TIER_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}

NAME_SYSTEM_PROMPT = (
    "You name a short lesson that bundles these conversational-skill rules together.\n"
    "Return ONLY a JSON object, no prose, no markdown code fences:\n"
    '{"name": "<short, specific lesson title, under 8 words>"}'
)


class _ProposedName(BaseModel):
    name: str


def order_rules_for_lessons(rules: list[Rule], mastery_by_rule: dict[str, Mastery]) -> list[Rule]:
    """Topological order by prerequisites first, then (tier, weakest
    mastery score, id) among rules with no ordering constraint between
    them. A prerequisite that isn't itself in `rules` (not accepted, or
    already sequenced into an earlier lesson) is skipped, not an error."""
    by_id = {rule.id: rule for rule in rules}
    visited: set[str] = set()
    ordered: list[Rule] = []

    def sort_key(rule: Rule) -> tuple[int, float, str]:
        mastery = mastery_by_rule.get(rule.id)
        score = mastery.score if mastery else 0.0
        return (TIER_ORDER.get(rule.evidence_tier, 99), score, rule.id)

    def visit(rule: Rule) -> None:
        if rule.id in visited:
            return
        visited.add(rule.id)
        for prereq_id in rule.prerequisites:
            prereq = by_id.get(prereq_id)
            if prereq is not None:
                visit(prereq)
        ordered.append(rule)

    for rule in sorted(rules, key=sort_key):
        visit(rule)
    return ordered


def name_lesson(client: LlmClient, rules: list[Rule]) -> str:
    """Never raises or returns empty: a naming failure falls back to a
    deterministic joined name rather than blocking lesson generation."""
    fallback = " / ".join(rule.name for rule in rules)
    rules_block = "\n".join(f"- {rule.name}: {rule.imperative}" for rule in rules)
    reply = client.chat(
        [
            {"role": "system", "content": NAME_SYSTEM_PROMPT},
            {"role": "user", "content": rules_block},
        ],
        max_tokens=100,
        temperature=0.3,
    )
    try:
        data = extract_json_object(reply)
        name = _ProposedName(**data).name.strip()
        return name or fallback
    except (json.JSONDecodeError, ValueError, ValidationError):
        return fallback
