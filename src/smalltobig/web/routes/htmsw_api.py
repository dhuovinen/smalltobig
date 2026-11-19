"""JSON API for HTMSW clients, starting with the be-better macOS app.

The engine owns the framework, the judge, the debrief extractor and the records;
clients send conversations and get verified verdicts back. Results are recorded
under the engine's active privacy profile (DECISIONS #24), exactly as the web pages
record them, so a client cannot bypass `abstracted`.

Like the rest of the web UI there is no authentication: serve it on localhost or a
trusted network only, such as Tailscale (`stb serve --host <tailscale-ip>`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from smalltobig.framework.export import export
from smalltobig.llm.openai_compat import OpenAICompatClient
from smalltobig.models.session import Turn
from smalltobig.practice import htmsw_debrief, htmsw_judge
from smalltobig.record import feedback as record_feedback
from smalltobig.record import service
from smalltobig.record.models import SessionRecord

if TYPE_CHECKING:
    from smalltobig.config import Settings
    from smalltobig.framework.loader import Framework
    from smalltobig.practice.htmsw_judge import StepVerdict

router = APIRouter(prefix="/api/htmsw")

MAX_TURNS = 60


class JudgeRequest(BaseModel):
    turns: list[Turn] = Field(min_length=2, max_length=MAX_TURNS)
    domain_id: str
    partner_id: str | None = None
    client: str = Field(default="api", max_length=40)
    record: bool = True


class DebriefRequest(BaseModel):
    account: str = Field(min_length=1, max_length=htmsw_debrief.MAX_ACCOUNT_CHARS)
    domain_id: str
    consent: Literal["obtained", "not_required_here", "own_side_only"] = "own_side_only"
    record: bool = True


class StepFeedback(BaseModel):
    outcome_id: int
    agrees: bool


class FeedbackRequest(BaseModel):
    kind: Literal["rehearsal", "real", "prep"]
    domain_id: str
    useful: Literal["yes", "somewhat", "no"]
    outcome_ids: list[int] = Field(default_factory=list, max_length=8)
    steps: list[StepFeedback] = Field(default_factory=list, max_length=8)
    issues: list[str] = Field(default_factory=list, max_length=len(record_feedback.ISSUES))
    note: str = Field(default="", max_length=record_feedback.MAX_NOTE_CHARS)


def _fw(request: Request) -> Framework:
    fw: Framework = request.app.state.framework
    return fw


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _client(settings: Settings) -> OpenAICompatClient:
    return OpenAICompatClient(settings.llm_base_url, **settings.llm_options())


def _check_domain(fw: Framework, domain_id: str) -> None:
    if domain_id not in {d.id for d in fw.domains}:
        raise HTTPException(status_code=422, detail=f"unknown domain {domain_id!r}")


def _verdicts_json(verdicts: list[StepVerdict]) -> list[dict[str, object]]:
    return [v.model_dump() for v in verdicts]


def _model_unavailable(exc: httpx.HTTPError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": "model_unavailable", "detail": type(exc).__name__},
    )


@router.get("/framework")
def framework(request: Request) -> dict[str, object]:
    return export(_fw(request))


@router.post("/judge", response_model=None)
def judge(request: Request, body: JudgeRequest) -> dict[str, object] | JSONResponse:
    fw, settings = _fw(request), _settings(request)
    _check_domain(fw, body.domain_id)
    if not any(t.speaker == "user" for t in body.turns):
        raise HTTPException(status_code=422, detail="transcript has no user turns")
    try:
        with _client(settings) as client:
            verdicts, messages, reply = htmsw_judge.judge_detailed(client, fw, body.turns)
    except httpx.HTTPError as exc:
        return _model_unavailable(exc)
    outcome_ids: list[int] = []
    if body.record:
        outcome_ids = service.save_with_ids(settings, fw, SessionRecord(
            source="rehearsal", domain_id=body.domain_id, created_at=datetime.now(UTC),
            verdicts=tuple(verdicts), cluster_id=service.current_cluster(settings, fw),
            partner_id=body.partner_id or body.client, turns=tuple(body.turns),
            model_messages=tuple(dict(m) for m in messages), model_reply=reply,
        ))
    return {
        "verdicts": _verdicts_json(verdicts),
        "recorded": body.record,
        "outcome_ids": outcome_ids,  # pass back to POST /feedback, in verdict order
        "privacy_profile": settings.privacy_profile,
        "framework_revision": export(fw)["revision"],
    }


@router.post("/debrief", response_model=None)
def debrief(request: Request, body: DebriefRequest) -> dict[str, object] | JSONResponse:
    fw, settings = _fw(request), _settings(request)
    _check_domain(fw, body.domain_id)
    try:
        with _client(settings) as client:
            verdicts, messages, reply = htmsw_debrief.extract(client, fw, body.account)
    except httpx.HTTPError as exc:
        return _model_unavailable(exc)
    outcome_ids: list[int] = []
    if body.record:
        outcome_ids = service.save_with_ids(settings, fw, SessionRecord(
            source="real", domain_id=body.domain_id, created_at=datetime.now(UTC),
            verdicts=tuple(verdicts), cluster_id=service.current_cluster(settings, fw),
            account=body.account.strip(), consent=body.consent,
            model_messages=tuple(dict(m) for m in messages), model_reply=reply,
        ))
    return {
        "verdicts": _verdicts_json(verdicts),
        "recorded": body.record,
        "outcome_ids": outcome_ids,  # pass back to POST /feedback, in verdict order
        "privacy_profile": settings.privacy_profile,
    }


@router.get("/progress")
def progress(request: Request) -> dict[str, object]:
    fw, settings = _fw(request), _settings(request)
    outcomes, table, _ = service.progress(settings, fw)
    return {
        "privacy_profile": settings.privacy_profile,
        "real_weight": fw.progress.real_weight,
        "outcomes": len(outcomes),
        "counters": [c.model_dump() for c in table],
    }


@router.post("/feedback")
def feedback(request: Request, body: FeedbackRequest) -> dict[str, object]:
    """Tester feedback on a judged session or a prep card (record/feedback.py).

    `outcome_ids` come from the judge or debrief response. The note is kept only
    under the engine's `full` profile; under `abstracted` it is dropped.
    """
    fw, settings = _fw(request), _settings(request)
    _check_domain(fw, body.domain_id)
    submission = record_feedback.Submission(
        kind=body.kind, domain_id=body.domain_id, useful=body.useful,
        outcome_ids=tuple(body.outcome_ids),
        agrees=tuple((s.outcome_id, s.agrees) for s in body.steps),
        issues=tuple(body.issues), note=body.note,
    )
    try:
        service.record_feedback_submission(
            settings, fw, submission, int(datetime.now(UTC).timestamp()))
    except record_feedback.FeedbackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "recorded": True,
        "note_kept": settings.privacy_profile == "full" and bool(body.note.strip()),
        "privacy_profile": settings.privacy_profile,
    }


@router.get("/feedback")
def feedback_summary(request: Request) -> dict[str, object]:
    """Agreement per step and source, usefulness and issue counts. Never the notes."""
    settings = _settings(request)
    summary, _ = service.feedback_summary(settings)
    return {
        "privacy_profile": settings.privacy_profile,
        "issues": [{"id": i.id, "label": i.label, "kinds": list(i.kinds)}
                   for i in record_feedback.ISSUES],
        "sessions": summary.sessions if summary else 0,
        "agreement": [vars(a) for a in summary.agreement] if summary else [],
        "useful": summary.useful if summary else {},
        "issue_counts": [{"kind": k, "label": label, "count": n}
                         for k, label, n in summary.issues] if summary else [],
    }
