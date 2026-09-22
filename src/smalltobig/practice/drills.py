"""Generate a drill stimulus, judge a response against a rule's rubric.

See docs/PLAN.md §2 Stage 5 and §4: "Every rubric item is a yes/no plus a
supporting quote from the transcript, and the quote gets the same
exact-match treatment as Stage 2." A rubric item the model marks passed
without a quote that actually appears in the response is downgraded to
failed here — reuses extract/verify.py's gate rather than trusting the
model's yes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from smalltobig.extract.verify import verify_claim
from smalltobig.llm.json_extract import extract_json_array
from smalltobig.models.drill import RubricResult

if TYPE_CHECKING:
    from smalltobig.llm.client import LlmClient
    from smalltobig.models.rule import Rule

STIMULUS_SYSTEM_PROMPT = (
    "You write a one- or two-sentence conversational stimulus for a practice drill.\n"
    "The drill tests this rule: {imperative}\n"
    "It applies: {when_to_apply}\n"
    "Write ONE short line a conversation partner might say that gives the practicer a "
    "clear, natural opening to apply the rule in their reply. The line should be their "
    "own statement or answer about themselves — something with content the practicer "
    "can react or follow up on — never a question aimed back at the practicer, and "
    "never a meta-comment about the drill itself. Return ONLY that line — no quotation "
    "marks, no prose, no JSON, no preamble."
)

JUDGE_SYSTEM_PROMPT = (
    "You judge a practice response against a rubric. For each rubric item, decide "
    "whether the response satisfies it.\n"
    "Return ONLY a JSON array, no prose, no markdown code fences, one element per "
    "rubric item in the order given:\n"
    '[{"rubric_id": "<id>", "passed": true|false, '
    '"quote": "<if passed: the exact substring of the response that satisfies it, '
    'else "">"}]\n'
    "quote MUST be copied exactly from the response — do not paraphrase it."
)


class _JudgedItem(BaseModel):
    rubric_id: str
    passed: bool
    quote: str = ""


def generate_stimulus(client: LlmClient, rule: Rule) -> str:
    prompt = STIMULUS_SYSTEM_PROMPT.format(
        imperative=rule.imperative, when_to_apply=rule.when_to_apply
    )
    reply = client.chat(
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Write the line now."},
        ],
        max_tokens=100,
        temperature=0.7,
    )
    return reply.strip().strip('"')


def judge_drill_response(
    client: LlmClient, rule: Rule, stimulus: str, response: str
) -> list[RubricResult]:
    rubric_block = "\n".join(f"- {item.id}: {item.check}" for item in rule.rubric)
    prompt = f"Stimulus: {stimulus}\nResponse: {response}\n\nRubric:\n{rubric_block}"
    reply = client.chat(
        [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=600,
        temperature=0.0,
    )

    try:
        raw_items = extract_json_array(reply)
    except (json.JSONDecodeError, ValueError):
        raw_items = []

    # Observed live: a model asked for "one element per rubric item" will
    # sometimes wrap each item in its own single-element array instead of
    # one flat array — flatten one level rather than silently dropping
    # every item, since the per-item content itself is still well-formed.
    flattened: list[object] = []
    for entry in raw_items:
        if isinstance(entry, list):
            flattened.extend(entry)
        else:
            flattened.append(entry)

    judged_by_id: dict[str, _JudgedItem] = {}
    for item in flattened:
        if not isinstance(item, dict):
            continue
        try:
            judged = _JudgedItem(**item)
        except ValidationError:
            continue
        judged_by_id[judged.rubric_id] = judged

    results = []
    for rubric_item in rule.rubric:
        matched = judged_by_id.get(rubric_item.id)
        if matched is None or not matched.passed:
            results.append(RubricResult(rubric_id=rubric_item.id, passed=False, quote=None))
            continue

        verified = verify_claim(response, matched.quote)
        results.append(
            RubricResult(
                rubric_id=rubric_item.id,
                passed=verified.accepted,
                quote=matched.quote if verified.accepted else None,
            )
        )
    return results
