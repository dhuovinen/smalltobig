"""Score one drill: judge the response, persist it, update mastery.

See docs/PLAN.md §2 Stages 5-6.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from smalltobig.models.drill import Drill, generate_drill_id
from smalltobig.models.mastery import SignalType
from smalltobig.practice.drills import judge_drill_response
from smalltobig.progress.leitner import apply_signal
from smalltobig.store import repo_drills, repo_mastery, repo_rules

if TYPE_CHECKING:
    import sqlite3

    from smalltobig.llm.client import LlmClient


class UnknownRuleError(Exception):
    def __init__(self, rule_id: str) -> None:
        super().__init__(f"unknown rule {rule_id!r}")


def score_drill(
    conn: sqlite3.Connection,
    client: LlmClient,
    rule_id: str,
    stimulus: str,
    response: str,
) -> Drill:
    rule = repo_rules.get(conn, rule_id)
    if rule is None:
        raise UnknownRuleError(rule_id)

    rubric_results = judge_drill_response(client, rule, stimulus, response)
    success = bool(rubric_results) and all(result.passed for result in rubric_results)
    now = datetime.now(UTC)

    drill = Drill(
        id=generate_drill_id(rule_id, stimulus, response),
        rule_id=rule_id,
        stimulus=stimulus,
        response=response,
        rubric_results=rubric_results,
        success=success,
        created_at=now,
    )
    repo_drills.create(conn, drill)

    mastery = repo_mastery.get_or_default(conn, rule_id, now=now)
    updated = apply_signal(mastery, SignalType.DRILL, success=success, now=now)
    repo_mastery.upsert(conn, updated)

    return drill
