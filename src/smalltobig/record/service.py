"""Record, read and purge under the active privacy profile. Shared by web and CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from smalltobig.intake import profile as self_profile
from smalltobig.intake.classify import classify
from smalltobig.record import counters as record_counters
from smalltobig.record import feedback as record_feedback
from smalltobig.record import store as record_store
from smalltobig.store import db

if TYPE_CHECKING:
    import sqlite3

    from smalltobig.config import Settings
    from smalltobig.framework.loader import Framework
    from smalltobig.record.counters import StepCounter
    from smalltobig.record.feedback import Submission, Summary
    from smalltobig.record.models import Outcome, SessionRecord


def current_cluster(settings: Settings, fw: Framework) -> str | None:
    conn = db.connect(settings.db_path)
    try:
        answers = self_profile.load(conn)
    finally:
        conn.close()
    return classify(fw, answers).id if answers else None


def save(settings: Settings, fw: Framework, record: SessionRecord) -> list[Outcome]:
    conn = record_store.connect(settings.record_db_path, settings.privacy_profile)
    try:
        return record_store.write(conn, fw, record, settings.privacy_profile)
    finally:
        conn.close()


def save_with_ids(settings: Settings, fw: Framework, record: SessionRecord) -> list[int]:
    """Save a session and return its outcome row ids, in verdict order, for feedback."""
    conn = record_store.connect(settings.record_db_path, settings.privacy_profile)
    try:
        return [i for i, _ in record_store.write_with_ids(
            conn, fw, record, settings.privacy_profile)]
    finally:
        conn.close()


def progress(
    settings: Settings, fw: Framework, session_limit: int = 20
) -> tuple[list[Outcome], list[StepCounter], list[sqlite3.Row]]:
    """Outcomes, counters for every (step x domain), and recent full-profile sessions."""
    outcomes: list[Outcome] = []
    recent: list[sqlite3.Row] = []
    if settings.record_db_path.exists():
        conn = record_store.connect(settings.record_db_path, settings.privacy_profile)
        try:
            outcomes = record_store.outcomes(conn)
            recent = record_store.sessions(conn, limit=session_limit)
        finally:
            conn.close()
    return outcomes, record_counters.counters(fw, outcomes), recent


def record_feedback_submission(
    settings: Settings, fw: Framework, submission: Submission, at: int
) -> int:
    """Store tester feedback under the active profile (record/feedback.py)."""
    conn = record_store.connect(settings.record_db_path, settings.privacy_profile)
    try:
        return record_feedback.record(conn, fw, submission, settings.privacy_profile, at)
    finally:
        conn.close()


def feedback_summary(settings: Settings) -> tuple[Summary | None, list[sqlite3.Row]]:
    """Agreement and usefulness tallies, plus full-profile comments. None if no store yet."""
    if not settings.record_db_path.exists():
        return None, []
    conn = record_store.connect(settings.record_db_path, settings.privacy_profile)
    try:
        return record_feedback.summary(conn), record_feedback.notes(conn)
    finally:
        conn.close()


def purge_all(settings: Settings) -> None:
    """FR-55: delete the active profile's store and the HTMSW self-profile.

    The other profile's store and smalltobig's rules, sources and lessons are left
    alone: they are not this profile's user-derived HTMSW state.
    """
    record_store.purge(settings.record_db_path)
    conn = db.connect(settings.db_path)
    try:
        self_profile.clear(conn)
    finally:
        conn.close()
