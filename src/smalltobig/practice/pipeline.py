"""Score one drill, or one finished roleplay session: judge it, persist
it, update mastery for every rule it touched.

See docs/PLAN.md §2 Stages 5-6.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from smalltobig.models.drill import Drill, generate_drill_id
from smalltobig.models.mastery import SignalType
from smalltobig.models.session import Session, generate_session_id
from smalltobig.practice.drills import judge_drill_response
from smalltobig.practice.judge import judge_session
from smalltobig.progress.leitner import apply_signal
from smalltobig.store import repo_drills, repo_lessons, repo_mastery, repo_rules, repo_sessions

if TYPE_CHECKING:
    import sqlite3

    from smalltobig.config import Settings
    from smalltobig.llm.client import LlmClient
    from smalltobig.models.session import Turn


class UnknownRuleError(Exception):
    def __init__(self, rule_id: str) -> None:
        super().__init__(f"unknown rule {rule_id!r}")


class UnknownLessonError(Exception):
    def __init__(self, lesson_id: str) -> None:
        super().__init__(f"unknown lesson {lesson_id!r}")


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


def end_roleplay_session(
    conn: sqlite3.Connection,
    settings: Settings,
    client: LlmClient,
    lesson_id: str,
    scenario_id: str,
    turns: list[Turn],
) -> Session:
    lesson = repo_lessons.get(settings, lesson_id)
    if lesson is None:
        raise UnknownLessonError(lesson_id)

    rules = [repo_rules.get(conn, rule_id) for rule_id in lesson.rule_ids]
    present_rules = [rule for rule in rules if rule is not None]

    rubric_results = judge_session(client, turns, present_rules)
    now = datetime.now(UTC)

    session = Session(
        id=generate_session_id(lesson_id, scenario_id, now),
        lesson_id=lesson_id,
        scenario_id=scenario_id,
        rule_ids=[rule.id for rule in present_rules],
        turns=turns,
        rubric_results=rubric_results,
        created_at=now,
        ended_at=now,
    )
    repo_sessions.create(conn, session)

    for rule in present_rules:
        rule_results = [result for result in rubric_results if result.rule_id == rule.id]
        success = bool(rule_results) and all(result.passed for result in rule_results)
        mastery = repo_mastery.get_or_default(conn, rule.id, now=now)
        updated = apply_signal(mastery, SignalType.ROLEPLAY, success=success, now=now)
        repo_mastery.upsert(conn, updated)

    return session
