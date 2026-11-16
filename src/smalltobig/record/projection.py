"""project(record) -> outcomes: the single definition of what `abstracted` keeps.

FR-58: the abstracted record is a deterministic projection of the full record, and
this same function runs at write time under both profiles. A full store can be read
back through it to see exactly what the privacy design discards.

Pure: no I/O, no clock. Every field of the result is an integer, a bool or an id
from framework/*.yaml, never text the user or a third party wrote.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from smalltobig.record.models import Outcome

if TYPE_CHECKING:
    from smalltobig.framework.loader import Framework
    from smalltobig.record.models import SessionRecord


def project(fw: Framework, record: SessionRecord) -> list[Outcome]:
    fw.domain(record.domain_id)  # unknown domain: KeyError, never stored
    at = int(record.created_at.timestamp())
    return [
        Outcome(
            step_order=fw.step(v.step_id).order,
            domain_id=record.domain_id,
            source=record.source,
            passed=v.passed,
            at=at,
        )
        for v in record.verdicts
    ]
