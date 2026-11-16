"""HTMSW debrief: the four step outcomes from an account of a REAL conversation.

The user writes freely about a conversation that already happened. The model walks
the four checks one at a time (DECISIONS #17: free selection attached real quotes
to the wrong item) and quotes the account for each pass. Every quote is verified
byte-for-byte against the account (FR-45, DECISIONS #3).

What happens to the prose depends on the privacy profile, not on this module:
under `abstracted` only the four booleans are kept (FR-53); under `full` the
account is kept too (DECISIONS #24). This module never writes anything.

The partner-quote and turn-order checks used for rehearsals cannot apply to free
prose, so a debrief verdict rests on the judge's answer plus the verified quote.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from smalltobig.extract.verify import verify_claim
from smalltobig.practice.htmsw_judge import StepVerdict, ordered_rubric, parse_reply

if TYPE_CHECKING:
    from smalltobig.framework.loader import Framework
    from smalltobig.llm.client import ChatMessage, LlmClient

SYSTEM_PROMPT = (
    "You read someone's own account of a real conversation they had, and answer "
    "numbered checks about what THEY did in it.\n"
    "Go through the checks one at a time, in order, and answer every one. For each, "
    "give passed (true or false) and quote: words copied EXACTLY from the account "
    "that show it (empty if it did not pass, or if the account does not say).\n"
    "Return ONLY a JSON array of objects, no prose and no code fences. Example of "
    "the exact shape, for two checks:\n"
    '[{"item": 1, "passed": true, "quote": "exact words from the account"}, '
    '{"item": 2, "passed": false, "quote": ""}]\n'
    "Copy quotes character for character. Do not paraphrase or shorten with ellipses. "
    "If the account does not mention something, it did not pass."
)

MAX_ACCOUNT_CHARS = 8000


def debrief_messages(fw: Framework, account: str) -> list[ChatMessage]:
    checks = "\n".join(
        f"{i}. {item.check}" for i, item in enumerate(ordered_rubric(fw), start=1)
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Account:\n{account}\n\nChecks:\n{checks}"},
    ]


def extract(
    client: LlmClient, fw: Framework, account: str
) -> tuple[list[StepVerdict], list[ChatMessage], str]:
    """Four verdicts in step order, plus the request and raw reply."""
    text = account.strip()[:MAX_ACCOUNT_CHARS]
    messages = debrief_messages(fw, text)
    reply = client.chat(messages, max_tokens=1000, temperature=0.0)
    judged = parse_reply(reply)
    verdicts: list[StepVerdict] = []
    for position, item in enumerate(ordered_rubric(fw), start=1):
        j = judged.get(position)
        base = {"step_id": item.step, "rubric_id": item.id, "check": item.check}
        if j is None:
            verdicts.append(StepVerdict(**base, passed=False,
                                        reason="the model gave no answer for this check"))
        elif not j.passed:
            verdicts.append(StepVerdict(**base, passed=False,
                                        reason="your account doesn't show this step"))
        elif not j.quote.strip():
            verdicts.append(StepVerdict(
                **base, passed=False,
                reason="the model said yes but quoted nothing, so it doesn't count",
            ))
        elif not verify_claim(text, j.quote.strip()).accepted:
            verdicts.append(StepVerdict(
                **base, passed=False,
                reason="the model's quote is not in your account, so it was discarded",
            ))
        else:
            verdicts.append(StepVerdict(**base, passed=True, quote=j.quote.strip()))
    return verdicts, messages, reply
