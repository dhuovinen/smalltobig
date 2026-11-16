"""The HTMSW judge: four boolean verdicts, one per step, each with a verified span.

A separate call with a fresh context (FR-43). It receives the transcript and the
four rubric checks from framework/htmsw.yaml, never the partner's persona or
private instructions: this module does not import Partner or Scenario.

The judge proposes; code verifies. A verdict passes only if all of these hold:

1. The judge said it passed.
2. Its quote is found byte-for-byte in one of the user's turns (FR-45, the same
   gate as DECISIONS #3). An invented or paraphrased quote fails.
3. The structural checks the rubric item declares in htmsw.yaml hold. These exist
   because the verify gate proves a quote is real, never that the reasoning is
   right (DECISIONS #16: the judge once passed a build-on item because the turn
   contained a question mark).

No numeric scoring anywhere (FR-46). Items are matched by position, not by asking
the model to echo ids back (DECISIONS #16).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, ValidationError

from smalltobig.extract.verify import verify_claim
from smalltobig.llm.json_extract import extract_json_array

if TYPE_CHECKING:
    from smalltobig.framework.loader import Framework, RubricItem
    from smalltobig.llm.client import ChatMessage, LlmClient
    from smalltobig.models.session import Turn

SYSTEM_PROMPT = (
    "You judge a conversation transcript. Lines from the person being judged are "
    "marked 'user'; lines from the other person are marked 'partner'.\n"
    "Each numbered check below asks about the user's lines. Answer every check.\n"
    "For each check give: passed (true or false); quote, copied EXACTLY from ONE "
    "user line that shows it (empty if it did not pass); and, where the check says "
    "PARTNER QUOTE NEEDED, partner_quote, copied EXACTLY from ONE earlier partner "
    "line that the user's quoted line responds to.\n"
    "Return ONLY a JSON array of objects, no prose and no code fences. Example of "
    "the exact shape, for three checks where the second says PARTNER QUOTE NEEDED:\n"
    '[{"item": 1, "passed": true, "quote": "exact words from a user line", '
    '"partner_quote": ""}, '
    '{"item": 2, "passed": true, "quote": "exact words from a later user line", '
    '"partner_quote": "exact words from the earlier partner line it responds to"}, '
    '{"item": 3, "passed": false, "quote": "", "partner_quote": ""}]\n'
    "Copy quotes character for character. Do not paraphrase, shorten with ellipses, "
    "or join text from two lines."
)

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class StepVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_id: str
    rubric_id: str
    check: str
    passed: bool
    quote: str | None = None
    partner_quote: str | None = None
    reason: str | None = None  # why it did not pass; None when it passed


class _Judged(BaseModel):
    item: int
    passed: bool
    quote: str = ""
    partner_quote: str = ""


def format_transcript(turns: list[Turn]) -> str:
    return "\n".join(f"{t.speaker}: {t.text}" for t in turns)


def _format_rubric(items: list[RubricItem]) -> str:
    lines = []
    for i, item in enumerate(items, start=1):
        suffix = " (PARTNER QUOTE NEEDED)" if item.needs_partner_quote else ""
        lines.append(f"{i}. {item.check}{suffix}")
    return "\n".join(lines)


def judge_messages(fw: Framework, turns: list[Turn]) -> list[ChatMessage]:
    """The exact messages sent to the judge. Exposed so tests can inspect them."""
    items = ordered_rubric(fw)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Transcript:\n{format_transcript(turns)}\n\n"
            f"Checks:\n{_format_rubric(items)}",
        },
    ]


def ordered_rubric(fw: Framework) -> list[RubricItem]:
    order = {s.id: s.order for s in fw.steps}
    return sorted(fw.rubric, key=lambda r: order[r.step])


def parse_reply(reply: str) -> dict[int, _Judged]:
    cleaned = _THINK.sub("", reply)
    try:
        raw = extract_json_array(cleaned)
    except (json.JSONDecodeError, ValueError):
        return {}
    flat: list[object] = []
    for entry in raw:  # a model sometimes wraps each object in its own array
        flat.extend(entry if isinstance(entry, list) else [entry])
    out: dict[int, _Judged] = {}
    for entry in flat:
        if not isinstance(entry, dict):
            continue
        try:
            judged = _Judged(**entry)
        except ValidationError:
            continue
        out.setdefault(judged.item, judged)
    return out


def _turn_index(turns: list[Turn], speaker: str, quote: str, before: int | None = None) -> int:
    """Index of the first `speaker` turn containing `quote` verbatim, or -1."""
    limit = len(turns) if before is None else before
    for i, turn in enumerate(turns[:limit]):
        if turn.speaker == speaker and verify_claim(turn.text, quote).accepted:
            return i
    return -1


def verify_verdict(
    item: RubricItem, judged: _Judged | None, turns: list[Turn], step_id: str
) -> StepVerdict:
    def fail(reason: str, quote: str | None = None) -> StepVerdict:
        return StepVerdict(
            step_id=step_id, rubric_id=item.id, check=item.check,
            passed=False, quote=quote, reason=reason,
        )

    if judged is None:
        return fail("the judge gave no answer for this check")
    if not judged.passed:
        return fail("the judge found no evidence in your lines")
    quote = judged.quote.strip()
    if not quote:
        return fail("the judge said yes but quoted nothing, so it doesn't count")
    at = _turn_index(turns, "user", quote)
    if at < 0:
        return fail("the judge's quote is not in any of your lines, so it was discarded")

    partner_quote: str | None = None
    if item.needs_partner_quote:
        partner_quote = judged.partner_quote.strip()
        if _turn_index(turns, "partner", partner_quote, before=at) < 0:
            return fail(
                "no earlier line from your partner was quoted that this responds to",
                quote,
            )
    if item.no_user_question_before and any(
        t.speaker == "user" and "?" in t.text for t in turns[:at]
    ):
        return fail("you asked a question before this disclosure", quote)
    if item.min_prior_exchanges:
        prior = turns[:at]
        partner_turns = sum(t.speaker == "partner" for t in prior)
        user_turns = sum(t.speaker == "user" for t in prior)
        if min(partner_turns, user_turns) < item.min_prior_exchanges:
            return fail(
                f"this came before {item.min_prior_exchanges} rounds of back and forth",
                quote,
            )
    return StepVerdict(
        step_id=step_id, rubric_id=item.id, check=item.check,
        passed=True, quote=quote, partner_quote=partner_quote or None,
    )


def judge_detailed(
    client: LlmClient, fw: Framework, turns: list[Turn]
) -> tuple[list[StepVerdict], list[ChatMessage], str]:
    """Verdicts plus the exact request and raw reply, for the `full` profile's log."""
    messages = judge_messages(fw, turns)
    reply = client.chat(messages, max_tokens=1200, temperature=0.0)
    judged = parse_reply(reply)
    verdicts = [
        verify_verdict(item, judged.get(position), turns, item.step)
        for position, item in enumerate(ordered_rubric(fw), start=1)
    ]
    return verdicts, messages, reply


def judge(client: LlmClient, fw: Framework, turns: list[Turn]) -> list[StepVerdict]:
    """Four verdicts in step order. Never raises on a malformed judge reply."""
    return judge_detailed(client, fw, turns)[0]
