"""The drill loop — generate a stimulus, take a typed response, judge it
against the rule's rubric, update mastery. See docs/PLAN.md §2 Stage 5.

Stateless by design, like the rest of this app's forms: the generated
stimulus round-trips through a hidden form field rather than being kept
in server-side session state, so there's nothing to clean up and nothing
to get out of sync.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, Response

from smalltobig.llm.openai_compat import OpenAICompatClient
from smalltobig.practice.drills import generate_stimulus
from smalltobig.practice.pipeline import score_drill
from smalltobig.store import repo_rules
from smalltobig.web.rendering import templates

# FastAPI resolves Annotated[...] dependencies at runtime, so these need a
# real (not TYPE_CHECKING-only) import despite `from __future__ import annotations`.
from smalltobig.web.routes.sources import DbDep, SettingsDep  # noqa: TC001

router = APIRouter()


@router.get("/rules/{rule_id}/drill")
def new_drill(request: Request, settings: SettingsDep, conn: DbDep, rule_id: str) -> Response:
    rule = repo_rules.get(conn, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")

    with OpenAICompatClient(settings.llm_base_url, model=settings.llm_model) as client:
        stimulus = generate_stimulus(client, rule)

    return templates.TemplateResponse(
        request, "drill_new.html", {"rule": rule, "stimulus": stimulus}
    )


@router.post("/rules/{rule_id}/drill")
def submit_drill(
    request: Request,
    settings: SettingsDep,
    conn: DbDep,
    rule_id: str,
    stimulus: Annotated[str, Form()],
    response: Annotated[str, Form()],
) -> Response:
    rule = repo_rules.get(conn, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")

    with OpenAICompatClient(settings.llm_base_url, model=settings.llm_model) as client:
        drill = score_drill(conn, client, rule_id, stimulus, response)

    checks_by_id = {item.id: item.check for item in rule.rubric}
    graded = [
        (checks_by_id.get(result.rubric_id, result.rubric_id), result)
        for result in drill.rubric_results
    ]
    return templates.TemplateResponse(
        request, "drill_result.html", {"rule": rule, "drill": drill, "graded": graded}
    )
