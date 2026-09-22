"""Mastery dashboard — box and score per accepted rule. See
docs/PLAN.md §2 Stage 6.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response

from smalltobig.models.mastery import Mastery
from smalltobig.models.rule import RuleStatus
from smalltobig.store import repo_mastery, repo_rules
from smalltobig.web.rendering import templates
from smalltobig.web.routes.sources import DbDep  # noqa: TC001

router = APIRouter()


@router.get("/mastery")
def list_mastery(request: Request, conn: DbDep) -> Response:
    accepted = [rule for rule in repo_rules.list_all(conn) if rule.status == RuleStatus.ACCEPTED]
    mastery_by_rule = {mastery.rule_id: mastery for mastery in repo_mastery.list_all(conn)}

    now = datetime.now(UTC)
    rows = [
        (rule, mastery_by_rule.get(rule.id) or Mastery(rule_id=rule.id, updated_at=now))
        for rule in accepted
    ]
    rows.sort(key=lambda pair: pair[1].score)

    return templates.TemplateResponse(request, "mastery_list.html", {"rows": rows})
