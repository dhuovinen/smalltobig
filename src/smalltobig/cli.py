"""`stb` command-line entry point."""

from __future__ import annotations

import sys

import click

from smalltobig.config import get_settings
from smalltobig.doctor import run_doctor


@click.group()
def main() -> None:
    """From Small to Big."""


@main.command()
def doctor() -> None:
    """Check that the chat server and embedding backend actually work."""
    settings = get_settings()
    results = run_doctor(settings)

    all_ok = True
    for result in results:
        mark = click.style("OK", fg="green") if result.ok else click.style("FAIL", fg="red")
        click.echo(f"[{mark}] {result.name}: {result.detail}")
        all_ok = all_ok and result.ok

    if not all_ok:
        sys.exit(1)


@main.command()
def ingest() -> None:
    """Pick up every file currently sitting in the watched inbox folder."""
    from smalltobig.ingest.watchfolder import poll_inbox
    from smalltobig.store import db

    settings = get_settings()
    conn = db.connect(settings.db_path)
    try:
        sources = poll_inbox(conn, settings)
    finally:
        conn.close()

    for source in sources:
        click.echo(f"{source.id}  {source.title}")
    click.echo(f"{len(sources)} source(s) ingested from {settings.inbox_dir}")


@main.command()
@click.argument("source_id")
def extract(source_id: str) -> None:
    """Extract claims from a source and verify each against its text."""
    from smalltobig.extract.pipeline import UnknownSourceError, extract_source
    from smalltobig.llm.openai_compat import OpenAICompatClient
    from smalltobig.store import db

    settings = get_settings()
    conn = db.connect(settings.db_path)
    try:
        with OpenAICompatClient(settings.llm_base_url, model=settings.llm_model) as client:
            summary = extract_source(conn, settings, client, source_id)
    except UnknownSourceError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
    finally:
        conn.close()

    click.echo(f"{summary.chunks} chunk(s), {summary.proposed} claim(s) proposed")
    click.echo(
        f"{summary.accepted} accepted, {summary.rejected} rejected "
        f"({summary.rejection_rate:.0%} rejection rate)"
    )


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=None, help="Defaults to STB_PORT.")
def serve(host: str, port: int | None) -> None:
    """Run the web UI."""
    import uvicorn

    from smalltobig.web.app import create_app

    settings = get_settings()
    app = create_app(settings)
    uvicorn.run(app, host=host, port=port or settings.port)
