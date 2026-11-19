"""Tester feedback: per-step agreement with the judge, usefulness, issues (record/feedback.py)."""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.framework.loader import load_framework
from smalltobig.practice import htmsw_judge
from smalltobig.practice.htmsw_judge import StepVerdict
from smalltobig.record import feedback as fb
from smalltobig.record import store as record_store
from smalltobig.record.models import SessionRecord
from smalltobig.web.app import create_app
from smalltobig.web.routes import htmsw as htmsw_routes
from smalltobig.web.routes import htmsw_api

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

    from smalltobig.framework.loader import Framework
    from smalltobig.llm.client import ChatMessage

PROFILE = {"has_kids": "yes", "kids_stage": "teen", "caregiving": "no", "primary_focus": "family"}


@pytest.fixture(scope="module")
def fw() -> Framework:
    return load_framework(Settings(_env_file=None).framework_dir)  # type: ignore[call-arg]


def _session(
    conn: sqlite3.Connection, fw: Framework, source: str, passed: list[bool],
    domain_id: str = "cold_networking", minute: int = 0,
) -> list[int]:
    record = SessionRecord(
        source=source,  # type: ignore[arg-type]
        domain_id=domain_id,
        created_at=datetime(2026, 11, 18, 9, minute, tzinfo=UTC),
        verdicts=tuple(
            StepVerdict(step_id=f"step_{i}", rubric_id="x", check="c", passed=p)
            for i, p in enumerate(passed, start=1)
        ),
    )
    return [i for i, _ in record_store.write_with_ids(conn, fw, record, "abstracted")]


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return record_store.connect(tmp_path / "s.db", "abstracted")


# ------------------------------------------------------------------------- store


def test_summary_splits_disagreement_by_direction(
    conn: sqlite3.Connection, fw: Framework
) -> None:
    ids = _session(conn, fw, "rehearsal", [True, False, True, False])
    fb.record(conn, fw, fb.Submission(
        kind="rehearsal", domain_id="cold_networking", useful="somewhat", outcome_ids=tuple(ids),
        agrees=((ids[0], False), (ids[1], False), (ids[2], True)),
        issues=("partner_unrealistic", "too_slow"),
    ), "abstracted", at=1)
    s = fb.summary(conn)
    by_step = {a.step_order: a for a in s.agreement}
    assert by_step[1].disputed_pass == 1 and by_step[1].disputed_miss == 0  # judge said yes
    assert by_step[2].disputed_miss == 1 and by_step[2].disputed_pass == 0  # judge said not yet
    assert (by_step[3].asked, by_step[3].agreed) == (1, 1)
    assert 4 not in by_step  # unanswered steps are not counted as agreement
    assert s.useful == {"rehearsal": {"somewhat": 1}} and s.sessions == 1
    assert {label for _, label, _ in s.issues} == {
        fb.ISSUES_BY_ID["partner_unrealistic"].label, fb.ISSUES_BY_ID["too_slow"].label}


def test_resubmitting_replaces_the_earlier_answer(conn: sqlite3.Connection, fw: Framework) -> None:
    ids = _session(conn, fw, "real", [True, True, False, False])
    for useful, agrees in (("no", False), ("yes", True)):
        fb.record(conn, fw, fb.Submission(
            kind="real", domain_id="cold_networking", useful=useful,  # type: ignore[arg-type]
            outcome_ids=tuple(ids), agrees=((ids[0], agrees),), issues=("other",),
        ), "abstracted", at=2)
    s = fb.summary(conn)
    assert s.sessions == 1 and s.useful == {"real": {"yes": 1}}
    assert [(a.asked, a.agreed) for a in s.agreement] == [(1, 1)]
    assert s.issues == [("real", fb.ISSUES_BY_ID["other"].label, 1)]


@pytest.mark.parametrize("bad", [
    {"kind": "real"},  # ids are a rehearsal's
    {"domain_id": "giving_back"},  # ids are cold_networking's
    {"outcome_ids": (999,)},
    {"issues": ("cluster_wrong",)},  # a prep-card issue on a rehearsal
    {"issues": ("not_an_issue",)},
    {"outcome_ids": ()},
])
def test_feedback_must_match_its_session(
    conn: sqlite3.Connection, fw: Framework, bad: dict[str, object]
) -> None:
    ids = _session(conn, fw, "rehearsal", [True, True, True, True])
    fields: dict[str, object] = {
        "kind": "rehearsal", "domain_id": "cold_networking", "useful": "yes",
        "outcome_ids": tuple(ids), **bad,
    }
    with pytest.raises(fb.FeedbackError):
        fb.record(conn, fw, fb.Submission(**fields), "abstracted", at=3)  # type: ignore[arg-type]


def test_feedback_cannot_span_two_sessions(conn: sqlite3.Connection, fw: Framework) -> None:
    a = _session(conn, fw, "rehearsal", [True, True, True, True], minute=1)
    b = _session(conn, fw, "rehearsal", [True, True, True, True], minute=2)
    with pytest.raises(fb.FeedbackError):
        fb.record(conn, fw, fb.Submission(
            kind="rehearsal", domain_id="cold_networking", useful="yes",
            outcome_ids=(a[0], b[0]),
        ), "abstracted", at=4)


def test_prep_feedback_has_no_steps(conn: sqlite3.Connection, fw: Framework) -> None:
    fb.record(conn, fw, fb.Submission(kind="prep", domain_id="giving_back", useful="no",
                                      issues=("too_much_text",)), "abstracted", at=5)
    assert fb.summary(conn).useful == {"prep": {"no": 1}}
    ids = _session(conn, fw, "rehearsal", [True, True, True, True])
    with pytest.raises(fb.FeedbackError):
        fb.record(conn, fw, fb.Submission(kind="prep", domain_id="giving_back", useful="no",
                                          outcome_ids=tuple(ids)), "abstracted", at=6)


def test_note_is_dropped_under_abstracted_and_kept_under_full(
    tmp_path: Path, fw: Framework
) -> None:
    for profile in ("abstracted", "full"):
        c = record_store.connect(tmp_path / f"{profile}.db", profile)  # type: ignore[arg-type]
        try:
            fb.record(c, fw, fb.Submission(kind="prep", domain_id="giving_back", useful="yes",
                                           note="  the lines felt stiff  "),
                      profile, at=7)  # type: ignore[arg-type]
            notes = [r["note"] for r in fb.notes(c)]
        finally:
            c.close()
        assert notes == ([] if profile == "abstracted" else ["the lines felt stiff"])


def test_every_issue_code_is_unique() -> None:
    assert len({i.code for i in fb.ISSUES}) == len(fb.ISSUES)
    assert len({i.id for i in fb.ISSUES}) == len(fb.ISSUES)
    for kind in fb.KIND_CODES:
        assert fb.issues_for(kind)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- web


class Fake:
    def __enter__(self) -> Fake:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def health(self) -> bool:
        return True

    def chat(self, messages: list[ChatMessage], *, max_tokens: int = 256,
             temperature: float = 0.0) -> str:
        if messages[0]["content"] == htmsw_judge.SYSTEM_PROMPT:
            return json.dumps([{"item": 1, "passed": True, "quote": "I almost didn't come",
                                "partner_quote": ""}])
        return "Ha, me too."


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
            profile: str = "abstracted") -> TestClient:
    monkeypatch.setattr(htmsw_routes, "_client", lambda _s: Fake())
    monkeypatch.setattr(htmsw_api, "_client", lambda _s: Fake())
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, data_dir=tmp_path / "data", privacy_profile=profile)
    return TestClient(create_app(settings))


def test_rehearsal_result_feedback_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    turns = json.dumps([{"speaker": "partner", "text": "Hi"},
                        {"speaker": "user", "text": "I almost didn't come"}])
    page = client.post("/htmsw/rehearse/end", data={
        "partner_id": "sarah", "domain_id": "cold_networking", "turns_json": turns}).text
    assert "Was the judge right?" in page
    assert 'name="note"' not in page  # no comment box under abstracted
    ids = re.findall(r'name="outcome_id" value="(\d+)"', page)
    assert len(ids) == 4
    r = client.post("/htmsw/feedback", data={
        "kind": "rehearsal", "domain_id": "cold_networking", "useful": "yes",
        "outcome_id": ids, f"agree_{ids[0]}": "no", f"agree_{ids[1]}": "yes",
    }, follow_redirects=False)
    assert r.status_code == 303 and "feedback=saved" in r.headers["location"]
    progress = client.get(r.headers["location"]).text
    assert "Thanks, your feedback was saved." in progress
    assert "Feedback on the judge" in progress and "0/1" in progress and "1/1" in progress


def test_web_feedback_rejects_unknown_useful(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    r = client.post("/htmsw/feedback", data={"kind": "prep", "domain_id": "giving_back"})
    assert r.status_code == 400


def test_prep_card_has_feedback_form_and_full_profile_shows_comment_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch, profile="full")
    client.post("/htmsw/profile", data=PROFILE)
    card = client.post("/htmsw/prep", data={"domain_id": "giving_back"}).text
    assert 'name="kind" value="prep"' in card and 'name="note"' in card
    assert "Was the judge right?" not in card
    assert fb.ISSUES_BY_ID["cluster_wrong"].label in html.unescape(card)


# --------------------------------------------------------------------------- api


def test_api_judge_returns_outcome_ids_for_feedback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    turns = [{"speaker": "partner", "text": "Hi"},
             {"speaker": "user", "text": "I almost didn't come"}]
    body = client.post("/api/htmsw/judge",
                       json={"turns": turns, "domain_id": "cold_networking"}).json()
    ids = body["outcome_ids"]
    assert len(ids) == 4
    r = client.post("/api/htmsw/feedback", json={
        "kind": "rehearsal", "domain_id": "cold_networking", "useful": "somewhat",
        "outcome_ids": ids, "steps": [{"outcome_id": ids[3], "agrees": False}],
        "issues": ["too_slow"], "note": "kept only under full",
    })
    assert r.status_code == 200
    assert r.json() == {"recorded": True, "note_kept": False, "privacy_profile": "abstracted"}
    summary = client.get("/api/htmsw/feedback").json()
    assert summary["sessions"] == 1
    assert summary["agreement"][0]["step_order"] == 4
    assert summary["agreement"][0]["disputed_miss"] == 1
    assert {i["id"] for i in summary["issues"]} == set(fb.ISSUES_BY_ID)


def test_api_feedback_rejects_mismatched_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/htmsw/feedback", json={
        "kind": "real", "domain_id": "cold_networking", "useful": "yes", "outcome_ids": [1]})
    assert r.status_code == 422


def test_api_unrecorded_judgement_has_no_outcome_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    turns = [{"speaker": "partner", "text": "Hi"},
             {"speaker": "user", "text": "I almost didn't come"}]
    body = client.post("/api/htmsw/judge", json={
        "turns": turns, "domain_id": "cold_networking", "record": False}).json()
    assert body["outcome_ids"] == []
