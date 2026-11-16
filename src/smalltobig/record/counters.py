"""Step counters per (step, domain), computed from integer outcomes (FR-54).

Counters are derived, not stored separately: the integer `step_outcomes` log is the
source of truth, so there is one place to purge and nothing to keep in sync. The
weighting and levels come from the `progress` block in framework/htmsw.yaml.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Iterable

    from smalltobig.framework.loader import Framework
    from smalltobig.record.models import Outcome


class StepCounter(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_id: str
    step_order: int
    domain_id: str
    rehearsal_attempts: int
    rehearsal_successes: int
    real_attempts: int
    real_successes: int
    weighted_successes: int
    level_id: str
    level_label: str


def level_for(fw: Framework, weighted: int, real_successes: int) -> tuple[str, str]:
    for level in fw.progress.levels:
        if (
            weighted >= level.min_weighted_successes
            and real_successes >= level.min_real_successes
        ):
            return level.id, level.label
    raise AssertionError("progress levels must end with a catch-all")  # loader guarantees it


def counters(fw: Framework, outcomes: Iterable[Outcome]) -> list[StepCounter]:
    """One counter for every (step x domain) pair, including ones never attempted."""
    tally: dict[tuple[int, str], list[int]] = {
        (s.order, d.id): [0, 0, 0, 0] for s in fw.steps for d in fw.domains
    }
    for o in outcomes:
        key = (o.step_order, o.domain_id)
        if key not in tally:
            continue  # a step or domain since removed from the framework
        counts = tally[key]
        base = 0 if o.source == "rehearsal" else 2
        counts[base] += 1
        counts[base + 1] += int(o.passed)
    by_order = {s.order: s for s in fw.steps}
    result = []
    for (order, domain_id), (r_att, r_ok, x_att, x_ok) in sorted(tally.items()):
        weighted = r_ok + fw.progress.real_weight * x_ok
        level_id, label = level_for(fw, weighted, x_ok)
        result.append(
            StepCounter(
                step_id=by_order[order].id, step_order=order, domain_id=domain_id,
                rehearsal_attempts=r_att, rehearsal_successes=r_ok,
                real_attempts=x_att, real_successes=x_ok,
                weighted_successes=weighted, level_id=level_id, level_label=label,
            )
        )
    return result
