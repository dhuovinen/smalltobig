"""The claim review queue — read-only, plus a button to (re)run
extraction. See docs/PLAN.md §5 Phase 2: "Measure the rejection rate
here — it is your extraction-prompt regression metric."
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from smalltobig.extract.pipeline import extract_source
from smalltobig.llm.openai_compat import OpenAICompatClient
from smalltobig.store import repo_claims, repo_sources
from smalltobig.web.rendering import templates

# FastAPI resolves Annotated[...] dependencies at runtime, so these need a
# real (not TYPE_CHECKING-only) import despite `from __future__ import annotations`.
from smalltobig.web.routes.sources import DbDep, SettingsDep  # noqa: TC001

router = APIRouter()


@router.get("/sources/{source_id}/claims")
def list_claims(request: Request, conn: DbDep, source_id: str) -> Response:
    source = repo_sources.get(conn, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")

    claims = repo_claims.list_by_source(conn, source_id)
    accepted = sum(1 for claim in claims if claim.status.value == "accepted")
    return templates.TemplateResponse(
        request,
        "claims_list.html",
        {
            "source": source,
            "claims": claims,
            "accepted": accepted,
            "rejected": len(claims) - accepted,
        },
    )


@router.post("/sources/{source_id}/extract")
def run_extraction(
    request: Request, settings: SettingsDep, conn: DbDep, source_id: str
) -> Response:
    source = repo_sources.get(conn, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")

    with OpenAICompatClient(settings.llm_base_url, model=settings.llm_model) as client:
        extract_source(conn, settings, client, source_id)

    return RedirectResponse(f"/sources/{source_id}/claims", status_code=303)
