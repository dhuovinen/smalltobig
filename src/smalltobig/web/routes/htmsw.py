"""HTMSW intake and prep card pages (IMPLEMENTATION.md Phase 2).

Under /htmsw/ to stay clear of the model-generated Phase 6 pre-brief at /prep.
Nothing in this router calls a model or opens a network connection (FR-34):
the prep card is composed from framework/*.yaml, and the target notes are used
for this response only, never stored (REQUIREMENTS.md §5, Scenario is ephemeral).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from smalltobig.intake import profile as self_profile
from smalltobig.intake.classify import IntakeError, classify, missing
from smalltobig.prep.compose import compose
from smalltobig.store import db
from smalltobig.web.rendering import templates
from smalltobig.web.routes.sources import DbDep  # noqa: TC001

if TYPE_CHECKING:
    from fastapi.responses import Response

    from smalltobig.framework.loader import Framework

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
    return templates.TemplateResponse(request, "htmsw_prep_card.html", {"card": card})
