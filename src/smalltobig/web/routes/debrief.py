"""Pre-brief (a prep card before a real event) and debrief (logging what
happened after). See docs/PLAN.md §2 Stage 5.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Form, Request, Response

from smalltobig.llm.openai_compat import OpenAICompatClient
from smalltobig.models.mastery import Mastery
from smalltobig.models.rule import RuleStatus
from smalltobig.practice.debrief import generate_prep_card
from smalltobig.practice.pipeline import submit_debrief
from smalltobig.store import repo_mastery, repo_rules
from smalltobig.web.rendering import templates

# FastAPI resolves Annotated[...] dependencies at runtime, so these need a
# real (not TYPE_CHECKING-only) import despite `from __future__ import annotations`.
from smalltobig.web.routes.sources import DbDep, SettingsDep  # noqa: TC001

if TYPE_CHECKING:
    import sqlite3

    from smalltobig.models.rule import Rule

router = APIRouter()


def _weakest_accepted_rules(conn: sqlite3.Connection, limit: int = 3) -> list[Rule]:
    accepted = [rule for rule in repo_rules.list_all(conn) if rule.status == RuleStatus.ACCEPTED]
    now = datetime.now(UTC)
    mastery_by_rule = {mastery.rule_id: mastery for mastery in repo_mastery.list_all(conn)}

    def score_of(rule: Rule) -> float:
        mastery = mastery_by_rule.get(rule.id) or Mastery(rule_id=rule.id, updated_at=now)
        return mastery.score

    return sorted(accepted, key=score_of)[:limit]


@router.get("/prep/new")
def new_prep_card(request: Request) -> Response:
    return templates.TemplateResponse(request, "prep_new.html", {})


@router.post("/prep")
def create_prep_card(
    request: Request,
    settings: SettingsDep,
    conn: DbDep,
    event: Annotated[str, Form()],
) -> Response:
    weak_rules = _weakest_accepted_rules(conn)
    with OpenAICompatClient(settings.llm_base_url, model=settings.llm_model) as client:
        content = generate_prep_card(client, event)

    return templates.TemplateResponse(
        request,
        "prep_card.html",
        {"event": event, "weak_rules": weak_rules, "content": content},
    )


@router.get("/debrief/new")
def new_debrief(request: Request) -> Response:
    return templates.TemplateResponse(request, "debrief_new.html", {})


@router.post("/debrief")
def create_debrief(
    request: Request,
    settings: SettingsDep,
    conn: DbDep,
    text: Annotated[str, Form()],
) -> Response:
    with OpenAICompatClient(settings.llm_base_url, model=settings.llm_model) as client:
        debrief, field_notes = submit_debrief(conn, client, text)

    rules_by_id = {rule.id: rule for rule in repo_rules.list_all(conn)}
    return templates.TemplateResponse(
        request,
        "debrief_result.html",
        {"debrief": debrief, "field_notes": field_notes, "rules_by_id": rules_by_id},
    )
