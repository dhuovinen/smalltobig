"""Lessons — list and detail, read straight off disk. See
docs/PLAN.md §5 Phase 4 and store/repo_lessons.py for why there's no DB
table behind this.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from smalltobig.store import repo_lessons, repo_rules
from smalltobig.web.rendering import templates

# FastAPI resolves Annotated[...] dependencies at runtime, so these need a
# real (not TYPE_CHECKING-only) import despite `from __future__ import annotations`.
from smalltobig.web.routes.sources import DbDep, SettingsDep  # noqa: TC001

router = APIRouter()


@router.get("/lessons")
def list_lessons(request: Request, settings: SettingsDep) -> Response:
    lessons = repo_lessons.list_all(settings)
    return templates.TemplateResponse(request, "lessons_list.html", {"lessons": lessons})


@router.get("/lessons/{lesson_id}")
def lesson_detail(
    request: Request, settings: SettingsDep, conn: DbDep, lesson_id: str
) -> Response:
    lesson = repo_lessons.get(settings, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="lesson not found")

    rules = [repo_rules.get(conn, rule_id) for rule_id in lesson.rule_ids]
    rules = [rule for rule in rules if rule is not None]
    return templates.TemplateResponse(
        request, "lesson_detail.html", {"lesson": lesson, "rules": rules}
    )
