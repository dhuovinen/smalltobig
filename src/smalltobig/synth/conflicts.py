"""Compare near-neighbour rules and propose Conflict records.

See docs/PLAN.md §2 Stage 3 and docs/DECISIONS.md #12 — the conflict
detector is the least certain component. This catches conflicts
similarity search can find: rules that are topically related (similar
embeddings) but whose imperatives read as incompatible. It will not find
a *tier* conflict like use-their-name vs no-boomerasking, where the
imperatives don't even resemble each other — docs/DECISIONS.md #12's own
fallback ("surface near-neighbour rule pairs... and let you judge") is
exactly what this implements, not an approximation of something bigger.

The band below is calibrated the same way as embed/cluster.py's default
threshold: live testing with mlx-community/all-MiniLM-L6-v2-bf16 put
genuinely-related rule imperatives around 0.4-0.51 cosine similarity —
see docs/DECISIONS.md #11's amendment.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from smalltobig.embed.cluster import cosine_similarity
from smalltobig.llm.json_extract import extract_json_object

if TYPE_CHECKING:
    from smalltobig.llm.client import LlmClient
    from smalltobig.models.rule import Rule

DEFAULT_LOW_SIMILARITY = 0.4
DEFAULT_HIGH_SIMILARITY = 0.85

SYSTEM_PROMPT = (
    "You are given two conversational-skill rules that are topically related. Decide "
    "whether they genuinely conflict: following one makes it harder or wrong to follow "
    "the other, or they give contradictory advice for the same situation. Rules that "
    "are simply about different topics, or that are compatible even though related, "
    "are NOT a conflict — do not force one.\n"
    "Return ONLY a JSON object, no prose, no markdown code fences:\n"
    '{"conflict": true|false, '
    '"note": "<if true: one or two sentences on the apparent contradiction, else "">", '
    '"proposed_resolution": "<if true: one or two sentences on how to reconcile or scope '
    'them, else "">"}'
)


class ProposedConflict(BaseModel):
    conflict: bool
    note: str = ""
    proposed_resolution: str = ""


def find_conflict_candidates(
    rules: list[Rule],
    embeddings: dict[str, list[float]],
    *,
    low: float = DEFAULT_LOW_SIMILARITY,
    high: float = DEFAULT_HIGH_SIMILARITY,
) -> list[tuple[Rule, Rule]]:
    """Pairs whose imperatives are topically related (similarity >= low)
    but not near-duplicates of each other (similarity < high)."""
    candidates = []
    for i in range(len(rules)):
        for j in range(i + 1, len(rules)):
            rule_a, rule_b = rules[i], rules[j]
            similarity = cosine_similarity(embeddings[rule_a.id], embeddings[rule_b.id])
            if low <= similarity < high:
                candidates.append((rule_a, rule_b))
    return candidates


def judge_conflict(client: LlmClient, rule_a: Rule, rule_b: Rule) -> ProposedConflict | None:
    prompt = (
        f"Rule A ({rule_a.id}): {rule_a.imperative}\n"
        f"Rule B ({rule_b.id}): {rule_b.imperative}"
    )
    reply = client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=400,
        temperature=0.0,
    )
    try:
        data = extract_json_object(reply)
        return ProposedConflict(**data)
    except (json.JSONDecodeError, ValueError, ValidationError):
        return None
