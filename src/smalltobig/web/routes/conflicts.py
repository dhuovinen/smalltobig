"""Conflicts — list and resolve.

The model's `proposed_resolution` is a starting point; `resolution` is
only ever written here, by a human (docs/DECISIONS.md non-negotiable #2).
See docs/PLAN.md §2 Stage 3: "that conflict log is, plausibly, the most
valuable artifact the app produces."
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from smalltobig.store import repo_conflicts, repo_rules
from smalltobig.web.rendering import templates

# FastAPI resolves Annotated[...] dependencies at runtime, so this needs a
# real (not TYPE_CHECKING-only) import despite `from __future__ import annotations`.
from smalltobig.web.routes.sources import DbDep  # noqa: TC001

router = APIRouter()


@router.get("/conflicts")
def list_conflicts(request: Request, conn: DbDep) -> Response:
    conflicts = repo_conflicts.list_all(conn)
    rules_by_id = {rule.id: rule for rule in repo_rules.list_all(conn)}
    return templates.TemplateResponse(
        request,
        "conflicts_list.html",
        {"conflicts": conflicts, "rules_by_id": rules_by_id},
    )


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(
    request: Request,
    conn: DbDep,
    conflict_id: str,
    resolution: Annotated[str, Form()],
) -> Response:
    if repo_conflicts.get(conn, conflict_id) is None:
        raise HTTPException(status_code=404, detail="conflict not found")

    repo_conflicts.resolve(conn, conflict_id, resolution, resolved_at=datetime.now(UTC))
    return RedirectResponse("/conflicts", status_code=303)
