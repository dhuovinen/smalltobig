"""HTMSW intake and prep card pages (IMPLEMENTATION.md Phase 2).

Under /htmsw/ to stay clear of the model-generated Phase 6 pre-brief at /prep.
Nothing in this router calls a model or opens a network connection (FR-34):
the prep card is composed from framework/*.yaml, and the target notes are used
for this response only, never stored (REQUIREMENTS.md §5, Scenario is ephemeral).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from smalltobig.intake import profile as self_profile
from smalltobig.intake.classify import IntakeError, classify, missing
from smalltobig.llm.openai_compat import OpenAICompatClient
from smalltobig.models.session import Turn
from smalltobig.practice import htmsw_debrief, htmsw_judge, htmsw_roleplay
from smalltobig.prep.compose import compose
from smalltobig.record import service as record_service
from smalltobig.record.models import SessionRecord
from smalltobig.store import db
from smalltobig.web.rendering import templates
from smalltobig.web.routes.sources import DbDep, SettingsDep  # noqa: TC001

if TYPE_CHECKING:
    from fastapi.responses import Response

    from smalltobig.config import Settings
    from smalltobig.framework.loader import Framework, Partner

router = APIRouter(prefix="/htmsw")


def _framework(request: Request) -> Framework:
    fw: Framework = request.app.state.framework
    return fw


@router.get("/profile")
def profile_form(request: Request, conn: DbDep) -> Response:
    fw = _framework(request)
    answers = self_profile.load(conn)
    return templates.TemplateResponse(
        request,
        "htmsw_profile.html",
        {
            "questions": fw.questions,
            "answers": answers,
            "cluster": classify(fw, answers) if answers else None,
            "missing": missing(fw, answers),
            "error": None,
            "privacy_profile": _profile(request),
        },
    )


@router.post("/profile")
async def profile_save(request: Request) -> Response:
    # Async to read a form whose fields come from personas.yaml, so the connection
    # is opened here: DbDep's sync generator runs on a worker thread, and sqlite3
    # connections are bound to the thread that created them.
    fw = _framework(request)
    form = await request.form()
    submitted = {q.id: str(form.get(q.id) or "") for q in fw.questions}
    conn = db.connect(request.app.state.settings.db_path)
    try:
        self_profile.save(conn, fw, submitted)
    except IntakeError as exc:
        return templates.TemplateResponse(
            request,
            "htmsw_profile.html",
            {
                "questions": fw.questions,
                "answers": {k: v for k, v in submitted.items() if v},
                "cluster": None,
                "missing": [],
                "error": str(exc),
                "privacy_profile": _profile(request),
            },
            status_code=422,
        )
    finally:
        conn.close()
    return RedirectResponse("/htmsw/prep/new", status_code=303)


@router.get("/prep/new")
def prep_form(request: Request, conn: DbDep) -> Response:
    fw = _framework(request)
    answers = self_profile.load(conn)
    return templates.TemplateResponse(
        request,
        "htmsw_prep_new.html",
        {
            "domains": fw.domains,
            "cluster": classify(fw, answers) if answers else None,
            "missing": missing(fw, answers) if answers else [],
            "privacy_profile": _profile(request),
        },
    )


@router.post("/prep")
def prep_card(
    request: Request,
    conn: DbDep,
    domain_id: Annotated[str, Form()],
    target_notes: Annotated[str, Form()] = "",
) -> Response:
    fw = _framework(request)
    answers = self_profile.load(conn)
    if not answers:
        return RedirectResponse("/htmsw/profile", status_code=303)
    if domain_id not in {d.id for d in fw.domains}:
        return RedirectResponse("/htmsw/prep/new", status_code=303)
    card = compose(fw, classify(fw, answers).id, domain_id, target_notes=target_notes)
    return templates.TemplateResponse(
        request,
        "htmsw_prep_card.html",
        {
            "card": card,
            "partners": htmsw_roleplay.partners_for(fw, domain_id),
            "privacy_profile": _profile(request),
        },
    )


# ------------------------------------------------------------------ rehearsal (Phase 3)
#
# Stateless like web/routes/roleplay.py: the transcript round-trips through a hidden
# JSON field while the conversation is live. When it is scored, the session is
# recorded under the active privacy profile (Phase 4, DECISIONS #24): `abstracted`
# keeps four integer outcomes, `full` keeps the transcript and judge log as well.

MAX_TURNS = 40


def _client(settings: Settings) -> OpenAICompatClient:
    return OpenAICompatClient(settings.llm_base_url, model=settings.llm_model)


def _partner(fw: Framework, partner_id: str) -> Partner:
    try:
        return fw.partner(partner_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown partner") from exc


def _domain_for(fw: Framework, partner: Partner, domain_id: str | None) -> str:
    if not domain_id:
        return partner.domains[0]
    if domain_id not in partner.domains:
        raise HTTPException(status_code=400, detail="partner does not cover that domain")
    return domain_id


def _turns(turns_json: str) -> list[Turn]:
    try:
        raw = json.loads(turns_json)
        turns = [Turn(**item) for item in raw]
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="malformed transcript") from exc
    if not turns or len(turns) > MAX_TURNS:
        raise HTTPException(status_code=400, detail="transcript length out of range")
    return turns


def _dump(turns: list[Turn]) -> str:
    return json.dumps([t.model_dump() for t in turns])


def _profile(request: Request) -> str:
    profile: str = request.app.state.settings.privacy_profile
    return profile


def _cluster_id(request: Request) -> str | None:
    return record_service.current_cluster(request.app.state.settings, _framework(request))


def _record(request: Request, record: SessionRecord) -> None:
    record_service.save(request.app.state.settings, _framework(request), record)


def _turn_page(request: Request, partner: Partner, domain_id: str, turns: list[Turn]) -> Response:
    user_turns = sum(t.speaker == "user" for t in turns)
    return templates.TemplateResponse(
        request,
        "htmsw_rehearse_turn.html",
        {
            "partner": partner,
            "domain_id": domain_id,
            "turns": turns,
            "turns_json": _dump(turns),
            "can_score": user_turns >= 1,
            "at_limit": len(turns) >= MAX_TURNS - 1,
            "privacy_profile": _profile(request),
        },
    )


@router.get("/rehearse/new")
def rehearse_form(request: Request) -> Response:
    fw = _framework(request)
    return templates.TemplateResponse(
        request,
        "htmsw_rehearse_new.html",
        {
            "partners": fw.partners,
            "domain_names": {d.id: d.name for d in fw.domains},
            "privacy_profile": _profile(request),
        },
    )


@router.post("/rehearse/start")
def rehearse_start(
    request: Request,
    partner_id: Annotated[str, Form()],
    domain_id: Annotated[str, Form()] = "",
) -> Response:
    fw = _framework(request)
    partner = _partner(fw, partner_id)
    domain = _domain_for(fw, partner, domain_id)
    return _turn_page(request, partner, domain, htmsw_roleplay.opening(partner))


@router.post("/rehearse/turn")
def rehearse_turn(
    request: Request,
    settings: SettingsDep,
    partner_id: Annotated[str, Form()],
    turns_json: Annotated[str, Form()],
    line: Annotated[str, Form()],
    domain_id: Annotated[str, Form()] = "",
) -> Response:
    fw = _framework(request)
    partner = _partner(fw, partner_id)
    domain = _domain_for(fw, partner, domain_id)
    turns = _turns(turns_json)
    if line.strip() and len(turns) < MAX_TURNS - 1:
        turns.append(Turn(speaker="user", text=line.strip()))
        with _client(settings) as client:
            turns.append(Turn(speaker="partner", text=htmsw_roleplay.reply(client, partner, turns)))
    return _turn_page(request, partner, domain, turns)


@router.post("/rehearse/end")
def rehearse_end(
    request: Request,
    settings: SettingsDep,
    partner_id: Annotated[str, Form()],
    turns_json: Annotated[str, Form()],
    domain_id: Annotated[str, Form()] = "",
) -> Response:
    fw = _framework(request)
    partner = _partner(fw, partner_id)
    domain = _domain_for(fw, partner, domain_id)
    turns = _turns(turns_json)
    with _client(settings) as client:
        verdicts, messages, reply = htmsw_judge.judge_detailed(client, fw, turns)
    _record(
        request,
        SessionRecord(
            source="rehearsal", domain_id=domain, created_at=datetime.now(UTC),
            verdicts=tuple(verdicts), cluster_id=_cluster_id(request), partner_id=partner.id,
            turns=tuple(turns), model_messages=tuple(dict(m) for m in messages),
            model_reply=reply,
        ),
    )
    steps = {s.id: s for s in fw.steps}
    return templates.TemplateResponse(
        request,
        "htmsw_rehearse_result.html",
        {
            "partner": partner, "turns": turns, "verdicts": verdicts, "steps": steps,
            "privacy_profile": _profile(request),
        },
    )


# ------------------------------------------------------------- debrief (Phase 4)


@router.get("/debrief/new")
def debrief_form(request: Request) -> Response:
    fw = _framework(request)
    return templates.TemplateResponse(
        request,
        "htmsw_debrief_new.html",
        {"domains": fw.domains, "privacy_profile": _profile(request)},
    )


@router.post("/debrief")
def debrief_submit(
    request: Request,
    settings: SettingsDep,
    domain_id: Annotated[str, Form()],
    account: Annotated[str, Form()],
    consent: Annotated[str, Form()] = "own_side_only",
) -> Response:
    fw = _framework(request)
    if domain_id not in {d.id for d in fw.domains}:
        raise HTTPException(status_code=400, detail="unknown domain")
    if consent not in {"obtained", "not_required_here", "own_side_only"}:
        raise HTTPException(status_code=400, detail="unknown consent value")
    if not account.strip():
        return RedirectResponse("/htmsw/debrief/new", status_code=303)
    with _client(settings) as client:
        verdicts, messages, reply = htmsw_debrief.extract(client, fw, account)
    _record(
        request,
        SessionRecord(
            source="real", domain_id=domain_id, created_at=datetime.now(UTC),
            verdicts=tuple(verdicts), cluster_id=_cluster_id(request),
            account=account.strip(), consent=consent,
            model_messages=tuple(dict(m) for m in messages), model_reply=reply,
        ),
    )
    steps = {s.id: s for s in fw.steps}
    return templates.TemplateResponse(
        request,
        "htmsw_debrief_result.html",
        {
            "verdicts": verdicts, "steps": steps, "domain": fw.domain(domain_id),
            "privacy_profile": _profile(request),
        },
    )


# ----------------------------------------------------------- progress and purge


@router.get("/progress")
def progress(request: Request) -> Response:
    fw = _framework(request)
    settings: Settings = request.app.state.settings
    outcomes, table, recent = record_service.progress(settings, fw)
    return templates.TemplateResponse(
        request,
        "htmsw_progress.html",
        {
            "steps": sorted(fw.steps, key=lambda s: s.order),
            "domains": fw.domains,
            "cells": {(c.step_id, c.domain_id): c for c in table},
            "real_weight": fw.progress.real_weight,
            "levels": fw.progress.levels,
            "total_outcomes": len(outcomes),
            "sessions": recent,
            "privacy_profile": settings.privacy_profile,
        },
    )


@router.get("/purge")
def purge_form(request: Request) -> Response:
    return templates.TemplateResponse(
        request, "htmsw_purge.html", {"privacy_profile": _profile(request), "done": False}
    )


@router.post("/purge")
def purge_submit(request: Request, confirm: Annotated[str, Form()] = "") -> Response:
    if confirm != "purge":
        return RedirectResponse("/htmsw/purge", status_code=303)
    settings: Settings = request.app.state.settings
    record_service.purge_all(settings)
    return templates.TemplateResponse(
        request, "htmsw_purge.html", {"privacy_profile": settings.privacy_profile, "done": True}
    )
