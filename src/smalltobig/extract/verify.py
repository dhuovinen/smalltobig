"""The verify gate. See docs/PLAN.md §2 Stage 2 and docs/DECISIONS.md #3.

    start = normalized.find(claim.verbatim)
    if start == -1:
        reject(claim, reason="span not found in source")

No judgment call, no second model, one string search. A model that
invents a quote, or paraphrases when told to quote, fails here
deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifyResult:
    accepted: bool
    start: int | None
    end: int | None
    reason: str | None


def verify_claim(normalized_source: str, verbatim: str) -> VerifyResult:
    if not verbatim:
        return VerifyResult(accepted=False, start=None, end=None, reason="empty verbatim span")

    start = normalized_source.find(verbatim)
    if start == -1:
        return VerifyResult(
            accepted=False, start=None, end=None, reason="span not found in source"
        )

    return VerifyResult(accepted=True, start=start, end=start + len(verbatim), reason=None)
