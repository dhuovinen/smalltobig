"""FastAPI application factory.

Import only from `stb serve` (cli.py) — FastAPI is an optional extra, and
nothing else in the app may depend on the web layer being installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from smalltobig.web.llm_errors import handle_llm_error
from smalltobig.web.routes.claims import router as claims_router
from smalltobig.web.routes.conflicts import router as conflicts_router
from smalltobig.web.routes.debrief import router as debrief_router
from smalltobig.web.routes.drills import router as drills_router
from smalltobig.web.routes.field_notes import router as field_notes_router
from smalltobig.web.routes.home import router as home_router
from smalltobig.web.routes.lessons import router as lessons_router
from smalltobig.web.routes.mastery import router as mastery_router
from smalltobig.web.routes.roleplay import router as roleplay_router
from smalltobig.web.routes.rules import router as rules_router
from smalltobig.web.routes.sources import router as sources_router
from smalltobig.web.routes.status import router as status_router

if TYPE_CHECKING:
    from smalltobig.config import Settings


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="From Small to Big")
    app.state.settings = settings
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )
    app.add_exception_handler(httpx.HTTPError, handle_llm_error)
    app.include_router(home_router)
    app.include_router(status_router)
    app.include_router(sources_router)
    app.include_router(claims_router)
    app.include_router(rules_router)
    app.include_router(conflicts_router)
    app.include_router(drills_router)
    app.include_router(lessons_router)
    app.include_router(mastery_router)
    app.include_router(roleplay_router)
    app.include_router(debrief_router)
    app.include_router(field_notes_router)
    return app
