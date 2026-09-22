"""List, paste-to-ingest, read, and poll-the-inbox — the source repository's
routes. See docs/PLAN.md §2 Stage 1 and §5 Phase 1.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from smalltobig.config import Settings
from smalltobig.ingest.paste import DuplicateSourceError, ingest_pasted_text
from smalltobig.ingest.watchfolder import poll_inbox
from smalltobig.models.source import SourceKind
from smalltobig.store import db, repo_sources
from smalltobig.web.rendering import templates

if TYPE_CHECKING:
    from collections.abc import Iterator

router = APIRouter()


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    conn = db.connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[sqlite3.Connection, Depends(get_db)]


@router.get("/")
def index() -> RedirectResponse:
    return RedirectResponse("/sources")


@router.get("/sources")
def list_sources(request: Request, settings: SettingsDep, conn: DbDep) -> Response:
    sources = repo_sources.list_all(conn)
    return templates.TemplateResponse(
        request,
        "sources_list.html",
        {"sources": sources, "inbox_dir": settings.inbox_dir},
    )


@router.get("/sources/new")
def new_source_form(request: Request) -> Response:
    return templates.TemplateResponse(
        request,
        "sources_new.html",
        {"kinds": list(SourceKind), "form": None, "error": None},
    )


@router.post("/sources")
def create_source(
    request: Request,
    settings: SettingsDep,
    conn: DbDep,
    title: Annotated[str, Form()],
    text: Annotated[str, Form()],
    kind: Annotated[SourceKind, Form()] = SourceKind.NOTES,
    author: Annotated[str, Form()] = "",
    url: Annotated[str, Form()] = "",
    license_note: Annotated[str, Form()] = "",
) -> Response:
    try:
        source = ingest_pasted_text(
            conn,
            settings,
            text=text,
            title=title,
            kind=kind,
            author=author or None,
            url=url or None,
            license_note=license_note or None,
        )
    except DuplicateSourceError as exc:
        return templates.TemplateResponse(
            request,
            "sources_new.html",
            {
                "kinds": list(SourceKind),
                "form": {
                    "title": title,
                    "author": author,
                    "kind": kind.value,
                    "url": url,
                    "license_note": license_note,
                    "text": text,
                },
                "error": str(exc),
            },
            status_code=409,
        )
    return RedirectResponse(f"/sources/{source.id}", status_code=303)


@router.get("/sources/{source_id}")
def source_detail(
    request: Request, settings: SettingsDep, conn: DbDep, source_id: str
) -> Response:
    source = repo_sources.get(conn, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    normalized_text = repo_sources.normalized_path(settings, source_id).read_text(
        encoding="utf-8"
    )
    return templates.TemplateResponse(
        request,
        "sources_detail.html",
        {"source": source, "normalized_text": normalized_text},
    )


@router.post("/sources/poll-inbox")
def poll_inbox_route(request: Request, settings: SettingsDep, conn: DbDep) -> Response:
    ingested = poll_inbox(conn, settings)
    sources = repo_sources.list_all(conn)
    flash = (
        f"Ingested {len(ingested)} source(s) from the inbox."
        if ingested
        else "Nothing new in the inbox."
    )
    return templates.TemplateResponse(
        request,
        "partials/_sources_table.html",
        {"sources": sources, "flash": flash},
    )
