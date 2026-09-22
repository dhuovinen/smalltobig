"""FastAPI application factory.

Import only from `stb serve` (cli.py) — FastAPI is an optional extra, and
nothing else in the app may depend on the web layer being installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from smalltobig.web.routes.claims import router as claims_router
from smalltobig.web.routes.conflicts import router as conflicts_router
from smalltobig.web.routes.rules import router as rules_router
from smalltobig.web.routes.sources import router as sources_router

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
    app.include_router(sources_router)
    app.include_router(claims_router)
    app.include_router(rules_router)
    app.include_router(conflicts_router)
    return app
