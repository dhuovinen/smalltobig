"""Ask the model for atomic claims from one chunk.

The model is told to quote, not paraphrase, in `verbatim` — but nothing
here trusts that instruction. verify.py's exact-match gate is what
actually enforces it (docs/DECISIONS.md #3); this module only defines the
contract and tolerates a model that returns malformed JSON or extra prose
around it, which small local models do often enough to plan for.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from smalltobig.llm.client import LlmClient

ClaimTypeLiteral = Literal["prescriptive", "descriptive", "empirical_finding", "anecdote"]

SYSTEM_PROMPT = (
    "You extract atomic claims from a passage of conversation advice.\n"
    "Return ONLY a JSON array, no prose, no markdown code fences. Each element:\n"
    '{"verbatim": "<exact substring copied character-for-character from the passage>", '
    '"paraphrase": "<one sentence, your own words>", '
    '"claim_type": "prescriptive|descriptive|empirical_finding|anecdote"}\n\n'
    "verbatim MUST be copied exactly from the passage - do not paraphrase, correct "
    "spelling, or reformat whitespace, or it will be rejected. "
    "If the passage contains no clear claims, return []."
)

_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)


class ExtractedClaim(BaseModel):
    verbatim: str
    paraphrase: str
    claim_type: ClaimTypeLiteral


def _parse_claims_json(reply: str) -> list[object]:
    match = _JSON_ARRAY.search(reply)
    candidate = match.group(0) if match else reply
    data = json.loads(candidate)
    if not isinstance(data, list):
        raise ValueError("model reply was not a JSON array")
    return data


def extract_claims_from_chunk(client: LlmClient, chunk_text: str) -> list[ExtractedClaim]:
    reply = client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": chunk_text},
        ],
        max_tokens=2000,
        temperature=0.0,
    )

    try:
        raw_items = _parse_claims_json(reply)
    except (json.JSONDecodeError, ValueError):
        return []

    claims = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            claims.append(ExtractedClaim(**item))
        except ValidationError:
            continue
    return claims
