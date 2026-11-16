"""Pre-brief and debrief. See docs/PLAN.md §2 Stage 5.

Pre-brief: given a short description of an upcoming event, propose two
topics and one exit line — no verify gate needed, since these are
suggestions about a conversation that hasn't happened yet, not claims
about one that has.

Debrief: given free text about a conversation that already happened,
extract FieldNote candidates tied to specific rules. Every extracted
quote is verified against the debrief text itself by the same gate as
claims, drills and roleplay (docs/DECISIONS.md #3) — the strongest
mastery signal (weight 3.0) gets the same scrutiny as everything else,
not less.

Rules are referred to by a plain 1-based number in the prompt, not by
asking the model to echo a rule_id string — practice/judge.py's Phase 5
finding was that even a 3B model can blend or garble echoed id strings,
and a debrief may list many more candidate rules than a roleplay's 1-3,
raising that same risk rather than lowering it.

The prompt asks the model to walk the rule list one at a time and emit an
"addressed" flag per rule, rather than freely picking which rules to
report on. An earlier free-selection version live-tested against a real
account containing genuine evidence for two different rules and produced
a single, well-formed, verify-gate-passing note that correctly quoted
real text but attached it to the WRONG rule number entirely — see
docs/DECISIONS.md #17. The verify gate cannot catch this failure mode:
it only checks that a quote exists in the source text, not that it was
matched to the right rule. The one-at-a-time structure was live-tested
as a fix and resolved the misattribution.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from smalltobig.extract.verify import verify_claim
from smalltobig.llm.json_extract import extract_json_array, extract_json_object

if TYPE_CHECKING:
    from smalltobig.llm.client import LlmClient
    from smalltobig.models.rule import Rule

PREP_SYSTEM_PROMPT = (
    "You help someone prepare for an upcoming social or professional event.\n"
    "Given a short description of the event, propose two specific, concrete "
    "conversation topics suited to this exact event — not generic advice — and one "
    "natural, graceful line they could use to exit a conversation there.\n"
    "Return ONLY a JSON object, no prose, no markdown code fences:\n"
    '{"topics": ["<topic one>", "<topic two>"], "exit_line": "<one sentence>"}'
)

DEBRIEF_SYSTEM_PROMPT = (
    "You read a free-text account of a real conversation the user just had. Below is "
    "a numbered list of conversational-skill rules the user is practicing.\n"
    "Go through the rules ONE AT A TIME, in order. For EACH rule, decide independently: "
    "does the account contain clear, specific evidence of the user applying or failing "
    "this SPECIFIC rule? Do not let evidence for one rule bleed into another rule's "
    "entry.\n"
    "Return ONLY a JSON array, no prose, no markdown code fences, with exactly one "
    "element per rule, in order:\n"
    '[{"rule": 1, "addressed": true, "success": true, "quote": "exact substring"}]\n'
    'For a rule the account does not address, use {"rule": N, "addressed": false, '
    '"success": false, "quote": ""}.\n'
    "quote MUST be copied exactly from the account — do not paraphrase it."
)


class ProposedPrepCard(BaseModel):
    topics: list[str]
    exit_line: str


class ExtractedFieldNote(BaseModel):
    rule_id: str
    success: bool
    quote: str


def generate_prep_card(client: LlmClient, event_description: str) -> ProposedPrepCard | None:
    reply = client.chat(
        [
            {"role": "system", "content": PREP_SYSTEM_PROMPT},
            {"role": "user", "content": event_description},
        ],
        max_tokens=300,
        temperature=0.5,
    )
    try:
        data = extract_json_object(reply)
        return ProposedPrepCard(**data)
    except (json.JSONDecodeError, ValueError, ValidationError):
        return None


class _JudgedNote(BaseModel):
    rule: int
    addressed: bool
    success: bool
    quote: str = ""


def extract_field_notes(
    client: LlmClient, text: str, rules: list[Rule]
) -> list[ExtractedFieldNote]:
    if not rules:
        return []

    rubric_block = "\n".join(
        f"{i}. {rule.imperative}" for i, rule in enumerate(rules, start=1)
    )
    prompt = f"Account:\n{text}\n\nRules:\n{rubric_block}"
    reply = client.chat(
        [
            {"role": "system", "content": DEBRIEF_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1000,
        temperature=0.0,
    )

    try:
        raw_items = extract_json_array(reply)
    except (json.JSONDecodeError, ValueError):
        raw_items = []

    # Same defensive flatten as practice/drills.py and practice/judge.py.
    flattened: list[object] = []
    for entry in raw_items:
        if isinstance(entry, list):
            flattened.extend(entry)
        else:
            flattened.append(entry)

    notes = []
    for raw_item in flattened:
        if not isinstance(raw_item, dict):
            continue
        try:
            judged = _JudgedNote(**raw_item)
        except ValidationError:
            continue

        if not judged.addressed:
            continue
        if not 1 <= judged.rule <= len(rules):
            continue
        rule = rules[judged.rule - 1]

        verified = verify_claim(text, judged.quote)
        if not verified.accepted:
            continue

        notes.append(
            ExtractedFieldNote(rule_id=rule.id, success=judged.success, quote=judged.quote)
        )
    return notes
