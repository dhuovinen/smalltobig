"""HTMSW intake and prep card pages (IMPLEMENTATION.md Phase 2).

Under /htmsw/ to stay clear of the model-generated Phase 6 pre-brief at /prep.
Nothing in this router calls a model or opens a network connection (FR-34):
the prep card is composed from framework/*.yaml, and the target notes are used
for this response only, never stored (REQUIREMENTS.md §5, Scenario is ephemeral).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from smalltobig.intake import profile as self_profile
from smalltobig.intake.classify import IntakeError, classify, missing
from smalltobig.llm.openai_compat import OpenAICompatClient
from smalltobig.models.session import Turn
from smalltobig.practice import htmsw_judge, htmsw_roleplay
from smalltobig.prep.compose import compose
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
        {"card": card, "partners": htmsw_roleplay.partners_for(fw, domain_id)},
    )


# ------------------------------------------------------------------ rehearsal (Phase 3)
#
# Stateless like web/routes/roleplay.py: the transcript round-trips through a hidden
# JSON field. Nothing from a rehearsal is written to disk in this phase; session
# persistence and counters arrive with Phase 4 and the privacy profiles (#24).

MAX_TURNS = 40


def _client(settings: Settings) -> OpenAICompatClient:
    return OpenAICompatClient(settings.llm_base_url, model=settings.llm_model)


def _partner(fw: Framework, partner_id: str) -> Partner:
    try:
        return fw.partner(partner_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown partner") from exc


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


def _turn_page(request: Request, partner: Partner, turns: list[Turn]) -> Response:
    user_turns = sum(t.speaker == "user" for t in turns)
    return templates.TemplateResponse(
        request,
        "htmsw_rehearse_turn.html",
        {
            "partner": partner,
            "turns": turns,
            "turns_json": _dump(turns),
            "can_score": user_turns >= 1,
            "at_limit": len(turns) >= MAX_TURNS - 1,
        },
    )


@router.get("/rehearse/new")
def rehearse_form(request: Request) -> Response:
    fw = _framework(request)
    return templates.TemplateResponse(
        request,
        "htmsw_rehearse_new.html",
        {"partners": fw.partners, "domain_names": {d.id: d.name for d in fw.domains}},
    )


@router.post("/rehearse/start")
def rehearse_start(request: Request, partner_id: Annotated[str, Form()]) -> Response:
    partner = _partner(_framework(request), partner_id)
    return _turn_page(request, partner, htmsw_roleplay.opening(partner))


@router.post("/rehearse/turn")
def rehearse_turn(
    request: Request,
    settings: SettingsDep,
    partner_id: Annotated[str, Form()],
    turns_json: Annotated[str, Form()],
    line: Annotated[str, Form()],
) -> Response:
    partner = _partner(_framework(request), partner_id)
    turns = _turns(turns_json)
    if line.strip() and len(turns) < MAX_TURNS - 1:
        turns.append(Turn(speaker="user", text=line.strip()))
        with _client(settings) as client:
            turns.append(Turn(speaker="partner", text=htmsw_roleplay.reply(client, partner, turns)))
    return _turn_page(request, partner, turns)


@router.post("/rehearse/end")
def rehearse_end(
    request: Request,
    settings: SettingsDep,
    partner_id: Annotated[str, Form()],
    turns_json: Annotated[str, Form()],
) -> Response:
    fw = _framework(request)
    partner = _partner(fw, partner_id)
    turns = _turns(turns_json)
    with _client(settings) as client:
        verdicts = htmsw_judge.judge(client, fw, turns)
    steps = {s.id: s for s in fw.steps}
    return templates.TemplateResponse(
        request,
        "htmsw_rehearse_result.html",
        {"partner": partner, "turns": turns, "verdicts": verdicts, "steps": steps},
    )
