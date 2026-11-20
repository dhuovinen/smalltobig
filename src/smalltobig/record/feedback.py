"""Tester feedback on the judge and on each session, stored under the privacy profile.

Built for the feedback round (rehearse, debrief, prep card, be-better scoring): the
thing to learn is whether people agree with the judge, step by step, and what got in
their way. Under both profiles only integers are stored:

- `step_feedback`: for one stored step outcome, did the tester agree with the
  verdict? Which way they disagreed follows from the outcome's own `passed`.
- `session_feedback`: was the session useful (yes / somewhat / no, three fixed
  answers, not a scale), plus `session_feedback_issues`, codes from ISSUES below.

A free-text comment is kept only under `full`, in `feedback_notes`. Under
`abstracted` it is dropped before anything touches the store (FR-51, DECISIONS #20).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from smalltobig.record import store as record_store

if TYPE_CHECKING:
    import sqlite3

    from smalltobig.framework.loader import Framework
    from smalltobig.record.store import Profile

Kind = Literal["rehearsal", "real", "prep"]
Useful = Literal["yes", "somewhat", "no"]

KIND_CODES: dict[Kind, int] = {"rehearsal": 1, "real": 2, "prep": 3}
KIND_NAMES = {v: k for k, v in KIND_CODES.items()}
USEFUL_CODES: dict[Useful, int] = {"yes": 1, "somewhat": 2, "no": 3}
USEFUL_NAMES = {v: k for k, v in USEFUL_CODES.items()}
MAX_NOTE_CHARS = 2000


@dataclass(frozen=True)
class Issue:
    code: int  # stored; never renumber, only add
    id: str
    label: str
    kinds: tuple[Kind, ...]


ISSUES: tuple[Issue, ...] = (
    Issue(1, "partner_unrealistic", "The partner didn't feel like a real person", ("rehearsal",)),
    Issue(2, "feedback_unclear", "I couldn't tell what to do differently next time",
          ("rehearsal", "real")),
    Issue(3, "stuck_for_words", "I didn't know what to say", ("rehearsal",)),
    Issue(4, "too_slow", "Waiting for replies or the score took too long", ("rehearsal", "real")),
    Issue(5, "privacy_unclear", "I wasn't sure what gets saved", ("rehearsal", "real", "prep")),
    Issue(6, "cluster_wrong", "The group I was put in doesn't fit me", ("prep",)),
    Issue(7, "phrasings_unnatural", "The example lines don't sound like me", ("prep",)),
    Issue(8, "too_much_text", "Too much to read before a conversation", ("prep",)),
    Issue(9, "writing_effort", "Writing the account was too much effort", ("real",)),
    Issue(10, "consent_unclear", "The recording-consent choice was confusing", ("real",)),
    Issue(11, "other", "Something else", ("rehearsal", "real", "prep")),
)
ISSUES_BY_ID = {i.id: i for i in ISSUES}
ISSUES_BY_CODE = {i.code: i for i in ISSUES}


class FeedbackError(ValueError):
    """Feedback that does not match a stored session, or uses unknown values."""


def issues_for(kind: Kind) -> list[Issue]:
    return [i for i in ISSUES if kind in i.kinds]


@dataclass(frozen=True)
class Submission:
    kind: Kind
    domain_id: str
    useful: Useful
    outcome_ids: tuple[int, ...] = ()  # the session's outcomes; empty for a prep card
    agrees: tuple[tuple[int, bool], ...] = ()  # (outcome_id, agreed with the judge)
    issues: tuple[str, ...] = ()
    note: str = ""


def _check_session(
    conn: sqlite3.Connection, fw: Framework, sub: Submission
) -> int | None:
    """Validate the outcome ids belong to one stored session of this kind and domain."""
    fw.domain(sub.domain_id)  # KeyError for unknown domains
    if sub.kind == "prep":
        if sub.outcome_ids or sub.agrees:
            raise FeedbackError("a prep card has no judged steps")
        return None
    if not sub.outcome_ids:
        raise FeedbackError("feedback on a session needs its outcome ids")
    ids = sorted(set(sub.outcome_ids))
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT o.id, o.at, o.source, d.slug FROM step_outcomes o "  # noqa: S608
        f"JOIN domain_refs d ON d.ref = o.domain_ref WHERE o.id IN ({marks})",
        ids,
    ).fetchall()
    if len(rows) != len(ids):
        raise FeedbackError("unknown outcome id")
    if len({(r[1], r[2], r[3]) for r in rows}) != 1:
        raise FeedbackError("outcome ids span more than one session")
    _, _, source, slug = rows[0]
    if record_store.SOURCE_NAMES[source] != sub.kind or slug != sub.domain_id:
        raise FeedbackError("outcome ids do not match the session's kind or domain")
    if any(oid not in ids for oid, _ in sub.agrees):
        raise FeedbackError("step feedback names an outcome outside this session")
    return ids[0]


def record(
    conn: sqlite3.Connection, fw: Framework, sub: Submission, profile: Profile, at: int
) -> int:
    """Store one submission. Re-submitting for the same session replaces the earlier one."""
    unknown = [i for i in sub.issues if i not in ISSUES_BY_ID
               or sub.kind not in ISSUES_BY_ID[i].kinds]
    if unknown:
        raise FeedbackError(f"unknown issue for {sub.kind}: {unknown[0]}")
    first = _check_session(conn, fw, sub)
    with conn:
        if first is not None:
            conn.execute("DELETE FROM session_feedback WHERE first_outcome_id = ?", (first,))
        for oid, agrees in sub.agrees:
            conn.execute(
                "INSERT OR REPLACE INTO step_feedback (outcome_id, at, agrees) VALUES (?, ?, ?)",
                (oid, at, int(agrees)),
            )
        cur = conn.execute(
            "INSERT INTO session_feedback (at, kind, domain_ref, first_outcome_id, useful) "
            "VALUES (?, ?, ?, ?, ?)",
            (at, KIND_CODES[sub.kind], record_store.domain_ref(conn, sub.domain_id), first,
             USEFUL_CODES[sub.useful]),
        )
        fid = int(cur.lastrowid or 0)
        for issue in sorted(set(sub.issues)):
            conn.execute(
                "INSERT INTO session_feedback_issues (feedback_id, issue) VALUES (?, ?)",
                (fid, ISSUES_BY_ID[issue].code),
            )
        note = sub.note.strip()[:MAX_NOTE_CHARS]
        if profile == "full" and note:
            conn.execute(
                "INSERT INTO feedback_notes (feedback_id, note) VALUES (?, ?)", (fid, note)
            )
    return fid


# --------------------------------------------------------------------------- summary


@dataclass(frozen=True)
class StepAgreement:
    step_order: int
    source: str  # "rehearsal" | "real"
    asked: int
    agreed: int
    disputed_pass: int  # judge said yes, tester said it wasn't
    disputed_miss: int  # judge said not yet, tester says they did it


@dataclass(frozen=True)
class Summary:
    agreement: list[StepAgreement]
    useful: dict[str, dict[str, int]]  # kind -> useful answer -> count
    issues: list[tuple[Kind, str, int]]  # (kind, issue label, count), most frequent first
    sessions: int


def summary(conn: sqlite3.Connection) -> Summary:
    agreement = [
        StepAgreement(
            step_order=r[0], source=record_store.SOURCE_NAMES[r[1]], asked=r[2], agreed=r[3],
            disputed_pass=r[4], disputed_miss=r[5],
        )
        for r in conn.execute(
            "SELECT o.step_order, o.source, COUNT(*), SUM(f.agrees), "
            "SUM(CASE WHEN f.agrees = 0 AND o.passed = 1 THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN f.agrees = 0 AND o.passed = 0 THEN 1 ELSE 0 END) "
            "FROM step_feedback f JOIN step_outcomes o ON o.id = f.outcome_id "
            "GROUP BY o.step_order, o.source ORDER BY o.step_order, o.source"
        )
    ]
    useful: dict[str, dict[str, int]] = {}
    sessions = 0
    for kind, ans, n in conn.execute(
        "SELECT kind, useful, COUNT(*) FROM session_feedback GROUP BY kind, useful"
    ):
        useful.setdefault(KIND_NAMES[kind], {})[USEFUL_NAMES[ans]] = n
        sessions += n
    issues = [
        (KIND_NAMES[kind], ISSUES_BY_CODE[code].label if code in ISSUES_BY_CODE else str(code), n)
        for kind, code, n in conn.execute(
            "SELECT s.kind, i.issue, COUNT(*) FROM session_feedback_issues i "
            "JOIN session_feedback s ON s.id = i.feedback_id "
            "GROUP BY s.kind, i.issue ORDER BY COUNT(*) DESC, s.kind, i.issue"
        )
    ]
    return Summary(agreement=agreement, useful=useful, issues=issues, sessions=sessions)


def notes(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    """Full-profile comments, newest first. Empty under `abstracted` (no table)."""
    has = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='feedback_notes'"
    ).fetchone()
    if not has:
        return []
    return conn.execute(
        "SELECT s.at, s.kind, d.slug AS domain_id, n.note FROM feedback_notes n "
        "JOIN session_feedback s ON s.id = n.feedback_id "
        "JOIN domain_refs d ON d.ref = s.domain_ref ORDER BY s.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
