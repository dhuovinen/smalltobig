"""The roleplay loop — pick a scenario, converse turn by turn, end and
get scored. See docs/PLAN.md §2 Stage 5.

Stateless like the rest of this app's forms (docs/PLAN.md §4 "boring
stack"): the transcript so far round-trips through a hidden JSON form
field rather than server-side session state, the same pattern
web/routes/drills.py uses for a drill's stimulus.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from smalltobig.llm.openai_compat import OpenAICompatClient
from smalltobig.models.session import Turn
from smalltobig.practice.pipeline import UnknownLessonError, end_roleplay_session
from smalltobig.practice.roleplay import generate_opening_line, generate_reply
from smalltobig.store import repo_lessons, repo_scenarios, repo_sessions
from smalltobig.web.rendering import templates

# FastAPI resolves Annotated[...] dependencies at runtime, so these need a
# real (not TYPE_CHECKING-only) import despite `from __future__ import annotations`.
from smalltobig.web.routes.sources import DbDep, SettingsDep  # noqa: TC001

router = APIRouter()


def _dump_turns(turns: list[Turn]) -> str:
    return json.dumps([turn.model_dump() for turn in turns])


def _load_turns(turns_json: str) -> list[Turn]:
    return [Turn(**item) for item in json.loads(turns_json)]


@router.get("/lessons/{lesson_id}/roleplay/new")
def new_roleplay(request: Request, settings: SettingsDep, lesson_id: str) -> Response:
    lesson = repo_lessons.get(settings, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="lesson not found")

    scenarios = repo_scenarios.list_all(settings)
    return templates.TemplateResponse(
        request, "roleplay_new.html", {"lesson": lesson, "scenarios": scenarios}
    )


@router.post("/lessons/{lesson_id}/roleplay/start")
def start_roleplay(
    request: Request,
    settings: SettingsDep,
    lesson_id: str,
    scenario_id: Annotated[str, Form()],
) -> Response:
    lesson = repo_lessons.get(settings, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="lesson not found")
    scenario = repo_scenarios.get(settings, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="scenario not found")

    with OpenAICompatClient(settings.llm_base_url, **settings.llm_options()) as client:
        opening_line = generate_opening_line(client, scenario)

    turns = [Turn(speaker="partner", text=opening_line)]
    return templates.TemplateResponse(
        request,
        "roleplay_turn.html",
        {
            "lesson": lesson,
            "scenario": scenario,
            "turns": turns,
            "turns_json": _dump_turns(turns),
        },
    )


@router.post("/lessons/{lesson_id}/roleplay/turn")
def continue_roleplay(
    request: Request,
    settings: SettingsDep,
    lesson_id: str,
    scenario_id: Annotated[str, Form()],
    turns_json: Annotated[str, Form()],
    reply: Annotated[str, Form()],
) -> Response:
    lesson = repo_lessons.get(settings, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="lesson not found")
    scenario = repo_scenarios.get(settings, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="scenario not found")

    turns = [*_load_turns(turns_json), Turn(speaker="user", text=reply)]
    with OpenAICompatClient(settings.llm_base_url, **settings.llm_options()) as client:
        partner_line = generate_reply(client, scenario, turns)
    turns.append(Turn(speaker="partner", text=partner_line))

    return templates.TemplateResponse(
        request,
        "roleplay_turn.html",
        {
            "lesson": lesson,
            "scenario": scenario,
            "turns": turns,
            "turns_json": _dump_turns(turns),
        },
    )


@router.post("/lessons/{lesson_id}/roleplay/end")
def finish_roleplay(
    request: Request,
    settings: SettingsDep,
    conn: DbDep,
    lesson_id: str,
    scenario_id: Annotated[str, Form()],
    turns_json: Annotated[str, Form()],
) -> Response:
    turns = _load_turns(turns_json)
    with OpenAICompatClient(settings.llm_base_url, **settings.llm_options()) as client:
        try:
            session = end_roleplay_session(
                conn, settings, client, lesson_id, scenario_id, turns
            )
        except UnknownLessonError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RedirectResponse(f"/sessions/{session.id}", status_code=303)


@router.get("/sessions")
def list_sessions(request: Request, conn: DbDep, settings: SettingsDep) -> Response:
    sessions = repo_sessions.list_all(conn)
    lessons_by_id = {lesson.id: lesson for lesson in repo_lessons.list_all(settings)}
    scenarios_by_id = {scenario.id: scenario for scenario in repo_scenarios.list_all(settings)}
    return templates.TemplateResponse(
        request,
        "sessions_list.html",
        {"sessions": sessions, "lessons_by_id": lessons_by_id, "scenarios_by_id": scenarios_by_id},
    )


@router.get("/sessions/{session_id}")
def session_detail(
    request: Request, conn: DbDep, settings: SettingsDep, session_id: str
) -> Response:
    session = repo_sessions.get(conn, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    scenario = repo_scenarios.get(settings, session.scenario_id)
    lesson = repo_lessons.get(settings, session.lesson_id)
    return templates.TemplateResponse(
        request,
        "session_detail.html",
        {"session": session, "scenario": scenario, "lesson": lesson},
    )
