"""The roleplay judge — scores a finished transcript against the target
lesson's rules.

Gets the transcript and the rubrics; never the persona's private
instructions (docs/PLAN.md §2 Stage 5, docs/DECISIONS.md non-negotiable
#4) — this module has no knowledge of Scenario or Persona at all, only
Turn and Rule. Every passed item must carry a quote verify_claim finds
byte-for-byte in one of the practicer's own turns, exactly like the
drill judge in practice/drills.py.

Rubric items are matched by their position (a plain 1-based number), not
by asking the model to echo back rule_id/rubric_id strings — live testing
found a real single-rule session where the model blended both ids into
one garbled token ("ask_followup" for rule id "ask-follow-up-questions"
and rubric id "asked_followup") despite supplying a genuinely valid,
verifiable quote. Numbering sidesteps that whole failure class: the
model only has to say which position it's judging, and the model in that
session got the underlying judgment right — the earlier id-matching
design was just throwing it away. See docs/DECISIONS.md #15's Phase 5
amendment for the transcript.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from smalltobig.extract.verify import verify_claim
from smalltobig.llm.json_extract import extract_json_array
from smalltobig.models.session import SessionRubricResult

if TYPE_CHECKING:
    from smalltobig.llm.client import LlmClient
    from smalltobig.models.rule import Rule
    from smalltobig.models.session import Turn

SYSTEM_PROMPT = (
    "You judge a roleplay transcript. The practicer's turns are marked 'user'; the "
    "other person's turns are marked 'partner'.\n"
    "Each rubric item below is numbered. For each one, decide whether the user's "
    "turns satisfy it.\n"
    "Return ONLY a JSON array of JSON objects, no prose, no markdown code fences. "
    "Example of the exact shape required, for two rubric items:\n"
    '[{"item": 1, "passed": true, "quote": "exact text from a user turn"}, '
    '{"item": 2, "passed": false, "quote": ""}]\n'
    "Each array element MUST be a JSON object wrapped in curly braces {}. quote "
    "MUST be copied exactly from a user turn — do not paraphrase it."
)


class _JudgedItem(BaseModel):
    item: int
    passed: bool
    quote: str = ""


def _format_transcript(turns: list[Turn]) -> str:
    return "\n".join(f"{turn.speaker}: {turn.text}" for turn in turns)


def _rule_rubric_pairs(rules: list[Rule]) -> list[tuple[Rule, str]]:
    """Every (rule, rubric_item_id) pair, in the fixed order both the
    prompt and the result-matching use."""
    return [(rule, item.id) for rule in rules for item in rule.rubric]


def _format_rubric(pairs: list[tuple[Rule, str]], rules: list[Rule]) -> str:
    checks_by_id = {(rule.id, item.id): item.check for rule in rules for item in rule.rubric}
    lines = [
        f"{i}. {checks_by_id[(rule.id, rubric_id)]}"
        for i, (rule, rubric_id) in enumerate(pairs, start=1)
    ]
    return "\n".join(lines)


def judge_session(
    client: LlmClient, turns: list[Turn], rules: list[Rule]
) -> list[SessionRubricResult]:
    pairs = _rule_rubric_pairs(rules)
    user_text = "\n".join(turn.text for turn in turns if turn.speaker == "user")
    prompt = (
        f"Transcript:\n{_format_transcript(turns)}\n\nRubric:\n{_format_rubric(pairs, rules)}"
    )
    reply = client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1000,
        temperature=0.0,
    )

    try:
        raw_items = extract_json_array(reply)
    except (json.JSONDecodeError, ValueError):
        raw_items = []

    # Same defensive flatten as practice/drills.py: a model asked for one
    # flat array sometimes wraps each item in its own single-element array.
    flattened: list[object] = []
    for entry in raw_items:
        if isinstance(entry, list):
            flattened.extend(entry)
        else:
            flattened.append(entry)

    judged_by_position: dict[int, _JudgedItem] = {}
    for raw_item in flattened:
        if not isinstance(raw_item, dict):
            continue
        try:
            judged = _JudgedItem(**raw_item)
        except ValidationError:
            continue
        judged_by_position[judged.item] = judged

    results = []
    for position, (rule, rubric_id) in enumerate(pairs, start=1):
        matched = judged_by_position.get(position)
        if matched is None or not matched.passed:
            results.append(
                SessionRubricResult(rule_id=rule.id, rubric_id=rubric_id, passed=False, quote=None)
            )
            continue

        verified = verify_claim(user_text, matched.quote)
        results.append(
            SessionRubricResult(
                rule_id=rule.id,
                rubric_id=rubric_id,
                passed=verified.accepted,
                quote=matched.quote if verified.accepted else None,
            )
        )
    return results
