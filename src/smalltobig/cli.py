"""`stb` command-line entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, TextIO, cast

import click

from smalltobig.config import get_settings
from smalltobig.doctor import run_doctor

if TYPE_CHECKING:
    from smalltobig.framework.loader import Framework
    from smalltobig.practice.htmsw_judge import StepVerdict


@click.group()
def main() -> None:
    """From Small to Big."""


@main.command()
def doctor() -> None:
    """Check that the chat server and embedding backend actually work."""
    settings = get_settings()
    # FR-59: the active privacy profile is always visible (DECISIONS #24).
    click.echo(
        f"[INFO] privacy profile: {settings.privacy_profile} "
        f"(HTMSW store: {settings.record_db_path})"
    )
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
        with OpenAICompatClient(settings.llm_base_url, **settings.llm_options()) as client:
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
        with OpenAICompatClient(settings.llm_base_url, **settings.llm_options()) as client:
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
        with OpenAICompatClient(settings.llm_base_url, **settings.llm_options()) as client:
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


def _framework_or_exit() -> Framework:
    from smalltobig.framework.loader import FrameworkError, load_framework

    try:
        return load_framework(get_settings().framework_dir)
    except FrameworkError as exc:
        click.echo(f"Framework error: {exc}", err=True)
        sys.exit(1)


def _parse_answers(pairs: tuple[str, ...]) -> dict[str, str]:
    answers: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise click.BadParameter(f"expected question=answer, got {pair!r}")
        answers[key.strip()] = value.strip()
    return answers


def _print_questions(fw: Framework) -> None:
    click.echo("Questions (question=answer):")
    for q in fw.questions:
        cond = ", ".join(f"{k}={v}" for k, v in q.ask_if.items())
        suffix = f"  (only if {cond})" if cond else ""
        click.echo(f"  {q.id}: {' | '.join(q.options)}{suffix}")


@main.group()
def profile() -> None:
    """Your HTMSW self-profile: intake flags only, never literal facts."""


@profile.command("show")
def profile_show() -> None:
    """Show stored answers and the cluster they classify to."""
    from smalltobig.intake import profile as self_profile
    from smalltobig.intake.classify import classify, missing
    from smalltobig.store import db

    fw = _framework_or_exit()
    conn = db.connect(get_settings().db_path)
    try:
        answers = self_profile.load(conn)
    finally:
        conn.close()
    if not answers:
        click.echo("No self-profile yet. Set one with: stb profile set has_kids=no ...")
        _print_questions(fw)
        return
    for key, value in answers.items():
        click.echo(f"  {key} = {value}")
    click.echo(f"Cluster: {classify(fw, answers).label}")
    if gaps := missing(fw, answers):
        click.echo(f"Unanswered: {', '.join(gaps)}")


@profile.command("set")
@click.argument("answers", nargs=-1, required=True)
def profile_set(answers: tuple[str, ...]) -> None:
    """Set answers, e.g. `stb profile set has_kids=yes kids_stage=teen`."""
    from smalltobig.intake import profile as self_profile
    from smalltobig.intake.classify import IntakeError, classify, missing
    from smalltobig.store import db

    fw = _framework_or_exit()
    conn = db.connect(get_settings().db_path)
    try:
        merged = {**self_profile.load(conn), **_parse_answers(answers)}
        try:
            stored = self_profile.save(conn, fw, merged)
        except IntakeError as exc:
            click.echo(f"Not saved: {exc}", err=True)
            _print_questions(fw)
            sys.exit(2)
    finally:
        conn.close()
    click.echo(f"Saved. Cluster: {classify(fw, stored).label}")
    if gaps := missing(fw, stored):
        click.echo(f"Still unanswered: {', '.join(gaps)}")


@profile.command("clear")
def profile_clear() -> None:
    """Delete the stored self-profile."""
    from smalltobig.intake import profile as self_profile
    from smalltobig.store import db

    conn = db.connect(get_settings().db_path)
    try:
        self_profile.clear(conn)
    finally:
        conn.close()
    click.echo("Self-profile cleared.")


@main.command()
@click.option(
    "--domain",
    "domain_id",
    required=True,
    help="cold_networking, casual_acquaintance, potential_collaborator or giving_back.",
)
@click.option(
    "--cluster", "cluster_id", default=None, help="Override the cluster from your self-profile."
)
@click.option(
    "--target",
    "target_notes",
    default="",
    help="What you know about them. Used for this card only; never stored.",
)
def prep(domain_id: str, cluster_id: str | None, target_notes: str) -> None:
    """Print an HTMSW prep card. No model, no network (FR-34)."""
    from smalltobig.intake import profile as self_profile
    from smalltobig.intake.classify import classify
    from smalltobig.prep.compose import compose, render_text
    from smalltobig.store import db

    fw = _framework_or_exit()
    if domain_id not in {d.id for d in fw.domains}:
        raise click.BadParameter(
            f"unknown domain {domain_id!r}; choose from {[d.id for d in fw.domains]}",
            param_hint="--domain",
        )
    if cluster_id is None:
        conn = db.connect(get_settings().db_path)
        try:
            answers = self_profile.load(conn)
        finally:
            conn.close()
        if not answers:
            click.echo(
                "No self-profile yet. Run `stb profile set ...` or pass --cluster.", err=True
            )
            sys.exit(2)
        cluster_id = classify(fw, answers).id
    elif cluster_id not in {c.id for c in fw.clusters}:
        raise click.BadParameter(
            f"unknown cluster {cluster_id!r}; choose from {[c.id for c in fw.clusters]}",
            param_hint="--cluster",
        )
    click.echo(render_text(compose(fw, cluster_id, domain_id, target_notes=target_notes)))


def _print_verdicts(fw: Framework, verdicts: list[StepVerdict], partner_name: str | None) -> None:
    for v in verdicts:
        step = fw.step(v.step_id)
        click.echo(f"\n{step.order}. {step.name}: {'yes' if v.passed else 'not yet'}")
        if v.partner_quote and partner_name:
            click.echo(f"   {partner_name} said: \"{v.partner_quote}\"")
        if v.quote:
            click.echo(f"   You said: \"{v.quote}\"")
        if not v.passed:
            click.echo(f"   Why not: {v.reason}. Next time: {step.coaching}")


def _saved_note(profile: str) -> str:
    if profile == "full":
        return "Saved in full (privacy profile: full): text, verdicts and the model log."
    return "Saved: four yes/no outcomes only (privacy profile: abstracted)."


@main.command()
@click.option("--partner", "partner_id", required=True, help="sarah or mike.")
@click.option(
    "--domain", "domain_id", default=None,
    help="Which kind of conversation this stands in for. Defaults to the partner's first.",
)
def rehearse(partner_id: str, domain_id: str | None) -> None:
    """Rehearse with an HTMSW partner, then score the four steps. Needs the model server.

    Type your lines; enter /end (or an empty line) to finish and be scored. The
    outcome is recorded under the active privacy profile (STB_PRIVACY_PROFILE).
    """
    from datetime import UTC, datetime

    from smalltobig.llm.openai_compat import OpenAICompatClient
    from smalltobig.models.session import Turn
    from smalltobig.practice import htmsw_judge, htmsw_roleplay
    from smalltobig.record import service
    from smalltobig.record.models import SessionRecord

    fw = _framework_or_exit()
    try:
        partner = fw.partner(partner_id)
    except KeyError:
        raise click.BadParameter(
            f"unknown partner {partner_id!r}; choose from {[p.id for p in fw.partners]}",
            param_hint="--partner",
        ) from None
    domain = domain_id or partner.domains[0]
    if domain not in partner.domains:
        raise click.BadParameter(
            f"{partner.name} stands in for {list(partner.domains)}", param_hint="--domain"
        )
    settings = get_settings()
    turns = htmsw_roleplay.opening(partner)
    click.echo(f"{partner.setting}\n")
    click.echo(f"{partner.name}: {turns[0].text}")
    with OpenAICompatClient(settings.llm_base_url, **settings.llm_options()) as client:
        while True:
            line = click.prompt("You", default="", show_default=False).strip()
            if not line or line == "/end":
                break
            turns.append(Turn(speaker="user", text=line))
            answer = htmsw_roleplay.reply(client, partner, turns)
            turns.append(Turn(speaker="partner", text=answer))
            click.echo(f"{partner.name}: {answer}")
        if not any(t.speaker == "user" for t in turns):
            click.echo("Nothing to score.")
            return
        click.echo("\nScoring...")
        verdicts, messages, reply = htmsw_judge.judge_detailed(client, fw, turns)
    service.save(settings, fw, SessionRecord(
        source="rehearsal", domain_id=domain, created_at=datetime.now(UTC),
        verdicts=tuple(verdicts), cluster_id=service.current_cluster(settings, fw),
        partner_id=partner.id, turns=tuple(turns),
        model_messages=tuple(dict(m) for m in messages), model_reply=reply,
    ))
    _print_verdicts(fw, verdicts, partner.name)
    click.echo(f"\n{_saved_note(settings.privacy_profile)}")


@main.command()
@click.option("--domain", "domain_id", required=True, help="Which kind of conversation it was.")
@click.option(
    "--consent",
    type=click.Choice(["own_side_only", "obtained", "not_required_here"]),
    default="own_side_only", show_default=True,
    help="Recording consent for the people involved (DECISIONS #24).",
)
@click.argument("account_file", type=click.File("r"), default="-")
def debrief(domain_id: str, consent: str, account_file: TextIO) -> None:
    """Debrief a real conversation. Reads your account from a file or stdin.

    The model extracts which of the four steps you took; each needs a quote from your
    account. Under the abstracted profile your account is used once and discarded.
    """
    from datetime import UTC, datetime

    from smalltobig.llm.openai_compat import OpenAICompatClient
    from smalltobig.practice import htmsw_debrief
    from smalltobig.record import service
    from smalltobig.record.models import SessionRecord

    fw = _framework_or_exit()
    if domain_id not in {d.id for d in fw.domains}:
        raise click.BadParameter(
            f"choose from {[d.id for d in fw.domains]}", param_hint="--domain"
        )
    if account_file.isatty():
        click.echo("Write what happened, then press Ctrl-D:")
    account = account_file.read().strip()
    if not account:
        click.echo("Nothing to debrief.", err=True)
        sys.exit(2)
    settings = get_settings()
    with OpenAICompatClient(settings.llm_base_url, **settings.llm_options()) as client:
        verdicts, messages, reply = htmsw_debrief.extract(client, fw, account)
    service.save(settings, fw, SessionRecord(
        source="real", domain_id=domain_id, created_at=datetime.now(UTC),
        verdicts=tuple(verdicts), cluster_id=service.current_cluster(settings, fw),
        account=account, consent=consent,
        model_messages=tuple(dict(m) for m in messages), model_reply=reply,
    ))
    _print_verdicts(fw, verdicts, None)
    click.echo(f"\n{_saved_note(settings.privacy_profile)}")


@main.command("reference-check")
@click.option(
    "--file", "path", type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None, help="Reference set YAML. Defaults to evals/htmsw_reference.yaml.",
)
def reference_check(path: Path | None) -> None:
    """Run the HTMSW judge reference set against the model server and report agreement.

    Every labelled rehearsal goes through the judge and every account through the
    debrief extractor, exactly as in the app. Nothing is recorded. Compare the result
    with the baseline in DECISIONS.md before shipping a judge, prompt or model change.
    """
    from smalltobig.llm.openai_compat import OpenAICompatClient
    from smalltobig.practice import reference_set

    fw = _framework_or_exit()
    refset = reference_set.load(path or reference_set.DEFAULT_PATH)
    settings = get_settings()
    click.echo(
        f"Model {settings.llm_model} at {settings.llm_base_url} · "
        f"{len(refset.rehearsals)} rehearsals, {len(refset.debriefs)} debriefs"
    )
    with OpenAICompatClient(settings.llm_base_url, **settings.llm_options()) as client:
        report = reference_set.run(client, fw, refset)
    steps = sorted(fw.steps, key=lambda s: s.order)
    for kind in ("rehearsal", "debrief"):
        click.echo(f"\n{kind.capitalize() + 's':<33}agreed   wrong yes   wrong not yet")
        for step in steps:
            agreed, total = report.agreement(kind, step.order)
            wrong_yes, wrong_no = report.errors(kind, step.order)
            click.echo(f"  {step.order}. {step.name:<28}{agreed:>2}/{total:<5}"
                       f"{wrong_yes:>6}{wrong_no:>14}")
    misses = [r for r in report.results if r.mismatches]
    click.echo(f"\n{len(misses)} of {len(report.results)} cases with a disagreement")
    for r in misses:
        for order in r.mismatches:
            got = "yes" if r.got[order - 1] else "not yet"
            reason = r.reasons[order - 1]
            click.echo(f"  {r.case_id}, step {order}: model said {got}"
                       + (f" ({reason})" if reason else ""))


@main.command("progress")
def progress_cmd() -> None:
    """Show HTMSW progress per step and kind of conversation."""
    from smalltobig.record import service

    fw = _framework_or_exit()
    settings = get_settings()
    outcomes, table, _ = service.progress(settings, fw)
    click.echo(
        f"Privacy profile: {settings.privacy_profile} · {len(outcomes)} step outcomes · "
        f"a real conversation counts {fw.progress.real_weight}x a rehearsal"
    )
    names = {d.id: d.name for d in fw.domains}
    for step in sorted(fw.steps, key=lambda s: s.order):
        click.echo(f"\n{step.order}. {step.name}")
        for c in (c for c in table if c.step_id == step.id):
            click.echo(
                f"   {names[c.domain_id]:<24} {c.level_label:<12} "
                f"rehearsed {c.rehearsal_successes}/{c.rehearsal_attempts}  "
                f"real {c.real_successes}/{c.real_attempts}"
            )


@main.command()
@click.option("--yes", is_flag=True, help="Don't ask for confirmation.")
def purge(yes: bool) -> None:
    """Delete your HTMSW profile and all sessions for the active privacy profile (FR-55)."""
    from smalltobig.record import service

    settings = get_settings()
    if not yes:
        click.confirm(
            f"Permanently delete your HTMSW self-profile and every session stored under "
            f"the '{settings.privacy_profile}' privacy profile?",
            abort=True,
        )
    service.purge_all(settings)
    click.echo(f"Purged ({settings.privacy_profile} profile).")


@main.command("export-framework")
@click.argument("out", type=click.Path(dir_okay=False, writable=True), default="-")
def export_framework(out: str) -> None:
    """Write the framework as JSON for clients (be-better bundles it offline)."""
    import json

    from smalltobig.framework.export import export

    text = json.dumps(export(_framework_or_exit()), indent=2, ensure_ascii=False) + "\n"
    if out == "-":
        click.echo(text, nl=False)
    else:
        Path(out).write_text(text, encoding="utf-8")
        click.echo(f"Wrote {out}", err=True)


@main.command()
@click.option(
    "--host", default=None,
    help="Address to listen on. Defaults to STB_HOST (127.0.0.1). 0.0.0.0 = every "
    "interface, including the LAN.",
)
@click.option("--port", type=int, default=None, help="Defaults to STB_PORT (8028).")
def serve(host: str | None, port: int | None) -> None:
    """Run the web UI. It has no login: serve beyond this machine on a trusted network only."""
    import uvicorn

    from smalltobig.web.app import create_app

    settings = get_settings()
    bind, listen_port = host or settings.host, port or settings.port
    app = create_app(settings)
    click.echo(f"Open http://{_display_host(bind)}:{listen_port}/htmsw/prep/new"
               f" · privacy profile: {settings.privacy_profile}")
    if bind not in ("127.0.0.1", "localhost", "::1"):
        click.echo("No login: anyone on this network can open it.")
    uvicorn.run(app, host=bind, port=listen_port)


def _display_host(bind: str) -> str:
    """The address to type into a browser: the LAN address when bound to all interfaces."""
    if bind not in ("0.0.0.0", "::"):
        return bind
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # TEST-NET-1: no packet is sent for UDP connect
            return str(s.getsockname()[0])
    except OSError:
        return "127.0.0.1"
