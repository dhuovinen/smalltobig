"""Small HTMX partials polled by the page chrome."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from smalltobig.llm.openai_compat import OpenAICompatClient
from smalltobig.web.rendering import templates
from smalltobig.web.routes.sources import SettingsDep  # noqa: TC001

router = APIRouter()

# The pill polls, so a hung server must not tie up a request for long.
HEALTH_TIMEOUT_SECONDS = 2.0


@router.get("/status/model")
def model_status(request: Request, settings: SettingsDep) -> Response:
    with OpenAICompatClient(
        settings.llm_base_url, **settings.llm_options(timeout=HEALTH_TIMEOUT_SECONDS)
    ) as client:
        online = client.health()
    return templates.TemplateResponse(
        request,
        "partials/_model_status.html",
        {"online": online, "base_url": settings.llm_base_url},
    )
