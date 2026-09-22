"""Draft one candidate rule from a cluster of related claims.

See docs/PLAN.md §2 Stage 3. Evidence tiers are the hardest judgment call
here — the model is told the A-D definitions and asked to ground the tier
in what kind of evidence backs the claims, not how confidently they read,
but this is exactly the reasoning docs/DECISIONS.md #11 flags as most
likely to disappoint on a small model. A human reviews every candidate
before it becomes a practised rule regardless.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ValidationError

from smalltobig.llm.json_extract import extract_json_object

if TYPE_CHECKING:
    from smalltobig.llm.client import LlmClient
    from smalltobig.models.claim import Claim

SYSTEM_PROMPT = (
    "You write one candidate conversational-skill rule, generalized from a cluster of "
    "related claims drawn from real sources.\n"
    "Return ONLY a JSON object, no prose, no markdown code fences:\n"
    '{"name": "<short imperative title, under 8 words>", '
    '"imperative": "<one or two sentence instruction, second person>", '
    '"rationale": "<why this works, one or two sentences, grounded only in the claims below>", '
    '"when_to_apply": "<the situation this applies in, one sentence>", '
    '"antipattern": "<the specific failure mode this guards against, one sentence>", '
    '"evidence_tier": "A|B|C|D", '
    '"rubric": [{"id": "<snake_case_id>", "check": "<a yes/no question ending in ?>"}]}\n\n'
    "Evidence tiers — base the tier on what kind of evidence backs the claims, not on how "
    "confidently they are phrased:\n"
    "A = peer-reviewed experiment with a measured behavioral outcome\n"
    "B = peer-reviewed observational or large field study\n"
    "C = practitioner consensus — the same claim from at least two independent sources\n"
    "D = single-source assertion, untested\n\n"
    "Write one or two rubric items. Each must be answerable yes or no by reading a "
    "transcript of a conversation, never a 1-10 rating."
)


class ProposedRubricItem(BaseModel):
    id: str
    check: str


class ProposedRule(BaseModel):
    name: str
    imperative: str
    rationale: str
    when_to_apply: str
    antipattern: str
    evidence_tier: Literal["A", "B", "C", "D"]
    rubric: list[ProposedRubricItem]


def _claims_block(claims: list[Claim]) -> str:
    return "\n".join(f'- "{claim.verbatim}" (paraphrase: {claim.paraphrase})' for claim in claims)


def draft_rule_from_cluster(client: LlmClient, claims: list[Claim]) -> ProposedRule | None:
    reply = client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _claims_block(claims)},
        ],
        max_tokens=800,
        temperature=0.2,
    )
    try:
        data = extract_json_object(reply)
        return ProposedRule(**data)
    except (json.JSONDecodeError, ValueError, ValidationError):
        return None
