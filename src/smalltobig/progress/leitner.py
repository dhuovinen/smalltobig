"""Apply one signal to a rule's mastery. See models/mastery.py for why
`box` and `score` are updated by different rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from smalltobig.models.mastery import (
    DRILL_ONLY_CEILING,
    MIN_BOX,
    SIGNAL_WEIGHTS,
    TOP_BOX,
    SignalType,
)

if TYPE_CHECKING:
    from datetime import datetime

    from smalltobig.models.mastery import Mastery


def apply_signal(
    mastery: Mastery, signal_type: SignalType, *, success: bool, now: datetime
) -> Mastery:
    has_non_drill = mastery.has_non_drill_evidence or signal_type != SignalType.DRILL
    weight = SIGNAL_WEIGHTS[signal_type]

    if success:
        ceiling = TOP_BOX if has_non_drill else DRILL_ONLY_CEILING
        box = min(mastery.box + 1, ceiling)
        score = mastery.score + weight
    else:
        box = MIN_BOX
        score = max(0.0, mastery.score - weight)

    return mastery.model_copy(
        update={
            "box": box,
            "score": score,
            "has_non_drill_evidence": has_non_drill,
            "updated_at": now,
        }
    )
