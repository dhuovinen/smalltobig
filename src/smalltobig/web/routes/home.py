"""Alternative front door: where you are in the pipeline, and the one thing to do next."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request, Response

from smalltobig.models.mastery import TOP_BOX, Mastery
from smalltobig.models.rule import RuleStatus
from smalltobig.store import repo_claims, repo_mastery, repo_rules, repo_sources, repo_stats
from smalltobig.web.rendering import templates
from smalltobig.web.routes.sources import DbDep  # noqa: TC001

if TYPE_CHECKING:
    import sqlite3

    from smalltobig.models.claim import Claim
    from smalltobig.models.rule import Rule
    from smalltobig.models.source import Source
    from smalltobig.store.repo_stats import HomeStats

router = APIRouter()


@dataclass(frozen=True)
class NextMove:
    stage: str
    headline: str
    detail: str
    label: str
    href: str


def next_move(stats: HomeStats, weakest: Rule | None) -> NextMove:
    if stats.sources == 0:
        return NextMove(
            "read",
            "Feed it something to read",
            "Paste an article, a book chapter or a transcript. Nothing is invented: "
            "every rule you end up with will point back at this text.",
            "Paste a source",
            "/sources/new",
        )
    if stats.claims == 0:
        return NextMove(
            "extract",
            "Pull the claims out",
            "Open a source and run extraction. Each claim must match the original "
            "text byte for byte, or it is thrown away.",
            "Choose a source",
            "/sources",
        )
    if stats.rules_accepted + stats.rules_candidate == 0:
        return NextMove(
            "decide",
            "Turn claims into candidate rules",
            "Rule synthesis runs from the terminal, not the browser. Run "
            "`stb synthesize`, then come back to review what it proposes.",
            "See sources",
            "/sources",
        )
    if stats.rules_candidate > 0:
        return NextMove(
            "decide",
            f"{stats.rules_candidate} candidate rule{_s(stats.rules_candidate)} "
            "waiting for your verdict",
            "Nothing becomes a rule you practise until you accept it. Read the evidence, "
            "then accept, reject or supersede.",
            "Review candidates",
            "/rules",
        )
    if stats.conflicts_open > 0:
        return NextMove(
            "decide",
            f"{stats.conflicts_open} disagreement{_s(stats.conflicts_open)} between your sources",
            "Experts contradict each other. Record which side you are taking and why.",
            "Arbitrate",
            "/conflicts",
        )
    if weakest is not None and stats.field_notes == 0 and stats.drills > 0:
        return NextMove(
            "field",
            "Now take it into the real world",
            "Drills and roleplay only rehearse. A note from a real conversation "
            "counts three times as much, and unlocks the top box.",
            "Log a real conversation",
            "/debrief/new",
        )
    if weakest is not None:
        return NextMove(
            "drill",
            f"Drill your weakest rule: {weakest.name}",
            weakest.imperative,
            "Start drill",
            f"/rules/{weakest.id}/drill",
        )
    return NextMove(
        "decide",
        "Nothing left to do here",
        "Every rule has been decided. Add another source to widen the set.",
        "Add a source",
        "/sources/new",
    )


def _s(n: int) -> str:
    return "" if n == 1 else "s"


@router.get("/home")
def home(request: Request, conn: DbDep) -> Response:
    stats = repo_stats.home_stats(conn)
    rules = repo_rules.list_all(conn)
    accepted = [rule for rule in rules if rule.status == RuleStatus.ACCEPTED]

    now = datetime.now(UTC)
    mastery_by_rule = {m.rule_id: m for m in repo_mastery.list_all(conn)}

    def mastery_of(rule: Rule) -> Mastery:
        return mastery_by_rule.get(rule.id) or Mastery(rule_id=rule.id, updated_at=now)

    weakest = min(accepted, key=lambda rule: mastery_of(rule).score, default=None)

    boxes = {box: 0 for box in range(1, TOP_BOX + 1)}
    for rule in accepted:
        boxes[mastery_of(rule).box] += 1

    sourced_rule = _latest_sourced_rule(conn, accepted)

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "stats": stats,
            "move": next_move(stats, weakest),
            "boxes": boxes,
            "box_max": max(boxes.values(), default=0),
            "sourced_rule": sourced_rule,
        },
    )


def _latest_sourced_rule(
    conn: sqlite3.Connection, accepted: list[Rule]
) -> tuple[Rule, Claim, Source | None] | None:
    for rule in sorted(accepted, key=lambda r: r.created_at, reverse=True):
        claims = repo_claims.get_many(conn, rule.claims)
        if claims:
            return rule, claims[0], repo_sources.get(conn, claims[0].source_id)
    return None
