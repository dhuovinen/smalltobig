"""Turn a failed call to the model server into a page that says what to do,
instead of a bare 500. Every route that talks to the model shares this."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from smalltobig.web.rendering import templates

if TYPE_CHECKING:
    from fastapi import Request, Response

    from smalltobig.config import Settings


def describe(exc: httpx.HTTPError) -> tuple[str, str]:
    """(short title, what happened) for the error page."""
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return "isn't running", "Nothing is answering at the model server's address."
    if isinstance(exc, httpx.TimeoutException):
        return (
            "took too long to answer",
            "The model server accepted the request but didn't reply in time. "
            "It may still be loading the model, or busy with another request.",
        )
    if isinstance(exc, httpx.HTTPStatusError):
        return (
            "returned an error",
            f"The model server answered with HTTP {exc.response.status_code}. "
            "A common cause is starting it without a model, or with the wrong one.",
        )
    return "couldn't be reached", "The request to the model server failed."


def handle_llm_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, httpx.HTTPError)  # registered for this type only
    settings: Settings = request.app.state.settings
    title, detail = describe(exc)
    port = urlparse(settings.llm_base_url).port or 3140
    model = settings.llm_model or "<model>"
    return templates.TemplateResponse(
        request,
        "llm_unavailable.html",
        {
            "title": title,
            "detail": detail,
            "base_url": settings.llm_base_url,
            "start_command": f"mlx_lm.server --model {model} --port {port}",
        },
        status_code=503,
    )
