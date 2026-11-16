"""Privacy invariants as executable tests (NFR-11, FR-50s, DECISIONS #24).

The most important tests in the suite. A sentinel string goes into every free-text
input an HTMSW user can type. A full set of flows then runs (prep, rehearsal,
debrief) and every column of every table in every database file is read back:

- abstracted: the sentinel appears nowhere (FR-51..FR-53);
- full: it is kept, by design, and only in the full profile's own store.

Plus: schema (no TEXT column where outcomes live), the projection-equivalence test
(FR-58), store separation (FR-59), permissions, and purge (FR-55).
"""

from __future__ import annotations

import html
import json
import sqlite3
import stat
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.framework.loader import load_framework
from smalltobig.models.session import Turn
from smalltobig.practice import htmsw_judge
from smalltobig.practice.htmsw_judge import StepVerdict
from smalltobig.record import service
from smalltobig.record import store as record_store
from smalltobig.record.models import SessionRecord
from smalltobig.record.projection import project
from smalltobig.web.app import create_app
from smalltobig.web.routes import htmsw as htmsw_routes

if TYPE_CHECKING:
    from pathlib import Path

    from smalltobig.framework.loader import Framework
    from smalltobig.llm.client import ChatMessage

SENTINEL = "SENTINEL-Okafor-Ridgeway-30117"
PROFILE = {"has_kids": "yes", "kids_stage": "teen", "caregiving": "no", "primary_focus": "family"}


class EchoJudge:
    """Actor lines echo the sentinel; judge and debrief replies quote it back."""

    def __enter__(self) -> EchoJudge:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def health(self) -> bool:
        return True

    def chat(self, messages: list[ChatMessage], *, max_tokens: int = 256,
             temperature: float = 0.0) -> str:
        if messages[0]["content"] == htmsw_judge.SYSTEM_PROMPT:
            quote = f"I almost didn't come, {SENTINEL}"
            return json.dumps([{"item": 1, "passed": True, "quote": quote, "partner_quote": ""}])
        if "real conversation" in messages[0]["content"]:
            return json.dumps([{"item": 1, "passed": True, "quote": SENTINEL}])
        return f"Partner says {SENTINEL} back"


def _settings(tmp_path: Path, profile: str) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None, data_dir=tmp_path / "data", privacy_profile=profile
    )


def _hidden(page: str, name: str) -> str:
    marker = f'name="{name}" value="'
    start = page.index(marker) + len(marker)
    return html.unescape(page[start:page.index('"', start)])


def _run_every_flow(client: TestClient) -> None:
    client.post("/htmsw/profile", data=PROFILE)
    # Free text the profile must refuse (FR-24).
    refused = client.post("/htmsw/profile", data={**PROFILE, "kids_stage": SENTINEL})
    assert refused.status_code == 422
    client.post("/htmsw/prep", data={"domain_id": "cold_networking", "target_notes": SENTINEL})
    page = client.post("/htmsw/rehearse/start", data={"partner_id": "sarah"}).text
    page = client.post("/htmsw/rehearse/turn", data={
        "partner_id": "sarah", "domain_id": "cold_networking",
        "turns_json": _hidden(page, "turns_json"), "line": f"I almost didn't come, {SENTINEL}",
    }).text
    end = client.post("/htmsw/rehearse/end", data={
        "partner_id": "sarah", "domain_id": "cold_networking",
        "turns_json": _hidden(page, "turns_json"),
    })
    assert end.status_code == 200
    debrief = client.post("/htmsw/debrief", data={
        "domain_id": "giving_back", "account": f"I told her {SENTINEL} and asked about it.",
        "consent": "obtained",
    })
    assert debrief.status_code == 200


def _cells_containing(data_dir: Path, needle: str) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for path in sorted(data_dir.glob("*.db")):
        conn = sqlite3.connect(path)
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                for row in conn.execute(f"SELECT * FROM {table}"):  # noqa: S608
                    if any(needle in str(v) for v in row):
                        hits.append((path.name, table))
        finally:
            conn.close()
    return hits


@pytest.fixture
def patch_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(htmsw_routes, "_client", lambda _s: EchoJudge())


@pytest.fixture(scope="module")
def fw() -> Framework:
    return load_framework(Settings(_env_file=None).framework_dir)  # type: ignore[call-arg]


# ------------------------------------------------------------------- sentinel sweep


def test_abstracted_profile_stores_no_prose_anywhere(tmp_path: Path, patch_model: None) -> None:
    settings = _settings(tmp_path, "abstracted")
    _run_every_flow(TestClient(create_app(settings)))
    assert settings.record_db_path.exists(), "outcomes should have been recorded"
    assert _cells_containing(settings.data_dir, SENTINEL) == []


def test_full_profile_keeps_everything_in_its_own_store(tmp_path: Path, patch_model: None) -> None:
    settings = _settings(tmp_path, "full")
    _run_every_flow(TestClient(create_app(settings)))
    hits = {table for name, table in _cells_containing(settings.data_dir, SENTINEL)
            if name == settings.record_db_path.name}
    assert {"sessions", "verdicts"} <= hits
    # Nothing leaks into the shared smalltobig.db, even under full.
    shared = [h for h in _cells_containing(settings.data_dir, SENTINEL)
              if h[0] != settings.record_db_path.name]
    assert shared == []
    conn = sqlite3.connect(settings.record_db_path)
    try:
        row = conn.execute("SELECT account, consent, model_reply FROM sessions "
                           "WHERE source = 'real'").fetchone()
    finally:
        conn.close()
    assert SENTINEL in row[0] and row[1] == "obtained" and row[2]


# ----------------------------------------------------------------------- schema


@pytest.mark.parametrize("profile", ["abstracted", "full"])
def test_outcome_table_has_no_text_column(tmp_path: Path, profile: str) -> None:
    conn = record_store.connect(tmp_path / "s.db", profile)  # type: ignore[arg-type]
    try:
        types = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(step_outcomes)")}
    finally:
        conn.close()
    assert types and "TEXT" not in types.values(), types


def test_abstracted_store_has_no_prose_tables(tmp_path: Path) -> None:
    conn = record_store.connect(tmp_path / "s.db", "abstracted")
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert not {"sessions", "verdicts"} & tables


@pytest.mark.parametrize("profile", ["abstracted", "full"])
def test_store_file_is_owner_only(tmp_path: Path, profile: str) -> None:
    path = tmp_path / "s.db"
    record_store.connect(path, profile).close()  # type: ignore[arg-type]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


# -------------------------------------------------------- projection & separation


def _record(source: str, passed: list[bool], text: str = SENTINEL) -> SessionRecord:
    verdicts = tuple(
        StepVerdict(step_id=f"step_{i}", rubric_id="x", check="c", passed=p,
                    quote=text if p else None)
        for i, p in enumerate(passed, start=1)
    )
    return SessionRecord(
        source=source,  # type: ignore[arg-type]
        domain_id="cold_networking",
        created_at=datetime(2026, 11, 16, 9, 30, tzinfo=UTC),
        verdicts=verdicts, partner_id="sarah",
        turns=(Turn(speaker="user", text=text),), account=text if source == "real" else None,
    )


def test_projection_is_identical_under_both_profiles(tmp_path: Path, fw: Framework) -> None:
    # FR-58: abstracted stores exactly project(full_record); a full store re-read
    # through the projection gives the same outcomes, with no second run.
    records = [_record("rehearsal", [True, False, True, False]),
               _record("real", [True, True, False, False])]
    stores = {}
    for profile in ("abstracted", "full"):
        conn = record_store.connect(tmp_path / f"{profile}.db", profile)  # type: ignore[arg-type]
        try:
            for r in records:
                record_store.write(conn, fw, r, profile)  # type: ignore[arg-type]
            stores[profile] = record_store.outcomes(conn)
        finally:
            conn.close()
    expected = [o for r in records for o in project(fw, r)]
    assert stores["abstracted"] == stores["full"] == expected


def test_profiles_use_separate_stores(tmp_path: Path) -> None:
    a, f = _settings(tmp_path, "abstracted"), _settings(tmp_path, "full")
    assert a.record_db_path != f.record_db_path
    record_store.connect(a.record_db_path, "abstracted").close()
    with pytest.raises(record_store.ProfileMismatchError):
        record_store.connect(a.record_db_path, "full")


def test_projection_contains_no_text(fw: Framework) -> None:
    for o in project(fw, _record("real", [True, True, True, True])):
        dumped = json.dumps(o.model_dump())
        assert SENTINEL not in dumped
        assert {type(v) for v in o.model_dump().values()} <= {int, bool, str}
        assert o.domain_id in {d.id for d in fw.domains}


# --------------------------------------------------------------------------- purge


def test_purge_removes_active_profile_state_only(
    tmp_path: Path, patch_model: None, fw: Framework
) -> None:
    abstracted, full = _settings(tmp_path, "abstracted"), _settings(tmp_path, "full")
    _run_every_flow(TestClient(create_app(abstracted)))
    service.save(full, fw, _record("rehearsal", [True, True, True, True]))
    service.purge_all(abstracted)
    assert not abstracted.record_db_path.exists()
    assert full.record_db_path.exists(), "the other profile's store must survive"
    conn = sqlite3.connect(abstracted.db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM self_profile").fetchone()[0] == 0
    finally:
        conn.close()


def test_web_purge_needs_typed_confirmation(tmp_path: Path, patch_model: None) -> None:
    settings = _settings(tmp_path, "abstracted")
    client = TestClient(create_app(settings))
    _run_every_flow(client)
    client.post("/htmsw/purge", data={"confirm": "yes"}, follow_redirects=False)
    assert settings.record_db_path.exists()
    page = client.post("/htmsw/purge", data={"confirm": "purge"})
    assert "Done" in page.text
    assert not settings.record_db_path.exists()


# ------------------------------------------------------------------------ deferred


@pytest.mark.skip(
    reason="FR-63/FR-64 per-stage cloud routing (DECISIONS #18/#22) is not built yet; "
    "the app has one STB_LLM_BASE_URL for every stage. Tracked for its own change."
)
def test_field_note_stages_refuse_cloud_without_acknowledgement() -> None:
    raise AssertionError("not implemented")



@pytest.mark.parametrize("profile", ["abstracted", "full"])
def test_progress_and_debrief_pages_show_the_profile(
    tmp_path: Path, patch_model: None, profile: str
) -> None:
    settings = _settings(tmp_path, profile)
    client = TestClient(create_app(settings))
    _run_every_flow(client)
    page = client.get("/htmsw/progress").text
    assert f"privacy: {profile}" in page  # FR-59: always visible
    assert "Initial disclosure" in page and "real 1/1" in page
    assert ("Recent sessions" in page) == (profile == "full")
    assert SENTINEL not in page or profile == "full"
    form = client.get("/htmsw/debrief/new").text
    assert ("Full-fidelity profile" in form) == (profile == "full")
