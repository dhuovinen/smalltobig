"""`stb` command-line entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

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
@click.option(
    "--threshold",
    type=float,
    default=None,
    help="Clustering similarity cutoff (0-1). Defaults to a value tuned for "
    "STB_EMBEDDING_MODEL's default model — tune by hand for a different one "
    "(docs/PLAN.md §2 Stage 3).",
)
def synthesize(threshold: float | None) -> None:
    """Cluster accepted claims into candidate rules and propose conflicts."""
    from smalltobig.llm.openai_compat import OpenAICompatClient
    from smalltobig.store import db
    from smalltobig.synth.pipeline import synthesize_rules

    settings = get_settings()
    try:
        from smalltobig.embed.mlx_backend import EmbeddingModel
    except ImportError as exc:
        click.echo(
            f"mlx-embeddings not installed ({exc}); "
            "run `pip install -e '.[mlx]'` (Apple Silicon only)",
            err=True,
        )
        sys.exit(1)

    embedding_model = EmbeddingModel(settings.embedding_model)

    def embed(texts: list[str]) -> list[list[float]]:
        return cast("list[list[float]]", embedding_model.embed(texts).tolist())

    conn = db.connect(settings.db_path)
    try:
        with OpenAICompatClient(settings.llm_base_url, model=settings.llm_model) as client:
            summary = (
                synthesize_rules(conn, client, embed, cluster_threshold=threshold)
                if threshold is not None
                else synthesize_rules(conn, client, embed)
            )
    finally:
        conn.close()

    click.echo(f"{summary.accepted_claims} accepted claim(s), {summary.clusters} cluster(s)")
    click.echo(
        f"{summary.rules_drafted} rule(s) drafted, "
        f"{summary.rules_skipped_existing} already covered by an existing rule"
    )
    click.echo(
        f"{summary.conflict_candidates} near-neighbour pair(s) checked, "
        f"{summary.conflicts_proposed} conflict(s) proposed"
    )


@main.command()
def lessons() -> None:
    """Sequence not-yet-lessoned accepted rules into lessons/*.yaml."""
    from smalltobig.llm.openai_compat import OpenAICompatClient
    from smalltobig.store import db
    from smalltobig.synth.pipeline import generate_lessons

    settings = get_settings()
    conn = db.connect(settings.db_path)
    try:
        with OpenAICompatClient(settings.llm_base_url, model=settings.llm_model) as client:
            summary = generate_lessons(conn, settings, client)
    finally:
        conn.close()

    click.echo(
        f"{summary.accepted_rules} accepted rule(s), "
        f"{summary.already_lessoned} already in a lesson"
    )
    click.echo(f"{summary.lessons_created} lesson(s) created in {settings.lessons_dir}")


@main.command()
@click.option(
    "--file",
    "rules_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="A seed rules.yaml. Defaults to docs/seed/rules.yaml.",
)
def seed(rules_file: Path | None) -> None:
    """Load the starter rules and disagreements as unverified candidates."""
    from smalltobig.seed import SeedFileError, default_seed_dir, load_seed
    from smalltobig.store import db

    settings = get_settings()
    path = rules_file or default_seed_dir(settings) / "rules.yaml"
    conn = db.connect(settings.db_path)
    try:
        summary = load_seed(conn, path)
    except SeedFileError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
    finally:
        conn.close()

    click.echo(
        f"{summary.rules_added} rule(s) added, {summary.rules_skipped} already present; "
        f"{summary.conflicts_added} disagreement(s) added, "
        f"{summary.conflicts_skipped} skipped"
    )
    click.echo("All are unverified candidates. Review them at /rules.")


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
