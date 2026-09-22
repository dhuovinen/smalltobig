"""Mastery: Leitner box per rule, updated by weighted signals.

See docs/PLAN.md §2 Stage 6 and CLAUDE.md non-negotiable #5. Two numbers
track different things, deliberately kept apart:

- `box` (1-5) drives "what should I drill next" — classic Leitner,
  promote one box on success, reset to 1 on failure. PLAN.md never asks
  the box arithmetic itself to be weighted by signal type.
- `score` is a separate running total using PLAN.md's weight table (3.0
  field note / 1.0 roleplay / 0.5 drill), used only to rank rules
  "weakest first" when sequencing lessons (Stage 4) — it does not gate
  box promotion.

The non-negotiable — a rule cannot reach the top box on drills alone —
is enforced as a ceiling on `box`: 5 is unreachable until
`has_non_drill_evidence` is true, regardless of how many drill successes
came before it.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

MIN_BOX = 1
TOP_BOX = 5
DRILL_ONLY_CEILING = 4


class SignalType(StrEnum):
    DRILL = "drill"
    ROLEPLAY = "roleplay"
    FIELD_NOTE = "field_note"


SIGNAL_WEIGHTS: dict[SignalType, float] = {
    SignalType.FIELD_NOTE: 3.0,
    SignalType.ROLEPLAY: 1.0,
    SignalType.DRILL: 0.5,
}


class Mastery(BaseModel):
    rule_id: str
    box: int = MIN_BOX
    score: float = 0.0
    has_non_drill_evidence: bool = False
    updated_at: datetime
