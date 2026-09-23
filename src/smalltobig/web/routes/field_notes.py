"""Field-note history — a progress view over real-world practice signal,
docs/PLAN.md §5 Phase 6's "progress views."
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from smalltobig.store import repo_field_notes, repo_rules
from smalltobig.web.rendering import templates
from smalltobig.web.routes.sources import DbDep  # noqa: TC001

router = APIRouter()


@router.get("/field-notes")
def list_field_notes(request: Request, conn: DbDep) -> Response:
    field_notes = repo_field_notes.list_all(conn)
    rules_by_id = {rule.id: rule for rule in repo_rules.list_all(conn)}
    return templates.TemplateResponse(
        request,
        "field_notes_list.html",
        {"field_notes": field_notes, "rules_by_id": rules_by_id},
    )
