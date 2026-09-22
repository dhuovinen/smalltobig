"""Rules — list, detail with claim provenance, and the human
accept/reject/supersede workflow. See docs/PLAN.md §5 Phase 3.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from smalltobig.models.rule import RuleStatus
from smalltobig.store import repo_claims, repo_rules, yaml_sync
from smalltobig.web.rendering import templates

# FastAPI resolves Annotated[...] dependencies at runtime, so these need a
# real (not TYPE_CHECKING-only) import despite `from __future__ import annotations`.
from smalltobig.web.routes.sources import DbDep, SettingsDep  # noqa: TC001

router = APIRouter()


@router.get("/rules")
def list_rules(request: Request, conn: DbDep) -> Response:
    rules = repo_rules.list_all(conn)
    return templates.TemplateResponse(request, "rules_list.html", {"rules": rules})


@router.get("/rules/{rule_id}")
def rule_detail(request: Request, conn: DbDep, rule_id: str) -> Response:
    rule = repo_rules.get(conn, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")

    claims = repo_claims.get_many(conn, rule.claims)
    other_rules = [r for r in repo_rules.list_all(conn) if r.id != rule_id]
    return templates.TemplateResponse(
        request,
        "rule_detail.html",
        {"rule": rule, "claims": claims, "other_rules": other_rules},
    )


@router.post("/rules/{rule_id}/accept")
def accept_rule(request: Request, settings: SettingsDep, conn: DbDep, rule_id: str) -> Response:
    if repo_rules.get(conn, rule_id) is None:
        raise HTTPException(status_code=404, detail="rule not found")

    repo_rules.set_status(conn, rule_id, RuleStatus.ACCEPTED, decided_at=datetime.now(UTC))
    accepted = repo_rules.get(conn, rule_id)
    assert accepted is not None  # just written above
    yaml_sync.write_rule(settings, accepted)
    return RedirectResponse(f"/rules/{rule_id}", status_code=303)


@router.post("/rules/{rule_id}/reject")
def reject_rule(request: Request, settings: SettingsDep, conn: DbDep, rule_id: str) -> Response:
    rule = repo_rules.get(conn, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")

    was_accepted = rule.status == RuleStatus.ACCEPTED
    repo_rules.set_status(conn, rule_id, RuleStatus.REJECTED, decided_at=datetime.now(UTC))
    if was_accepted:
        yaml_sync.remove_rule(settings, rule_id)
    return RedirectResponse(f"/rules/{rule_id}", status_code=303)


@router.post("/rules/{rule_id}/supersede")
def supersede_rule(
    request: Request,
    settings: SettingsDep,
    conn: DbDep,
    rule_id: str,
    superseded_by: Annotated[str, Form()],
) -> Response:
    rule = repo_rules.get(conn, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    if repo_rules.get(conn, superseded_by) is None:
        raise HTTPException(status_code=400, detail="superseding rule not found")

    was_accepted = rule.status == RuleStatus.ACCEPTED
    repo_rules.set_status(
        conn,
        rule_id,
        RuleStatus.SUPERSEDED,
        decided_at=datetime.now(UTC),
        superseded_by=superseded_by,
    )
    if was_accepted:
        yaml_sync.remove_rule(settings, rule_id)
    return RedirectResponse(f"/rules/{rule_id}", status_code=303)
