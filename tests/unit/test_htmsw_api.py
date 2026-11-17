"""JSON API for clients (be-better): framework export, judge, debrief, progress."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.framework.export import export
from smalltobig.framework.loader import load_framework
from smalltobig.practice import htmsw_judge
from smalltobig.web.app import create_app
from smalltobig.web.routes import htmsw_api

if TYPE_CHECKING:
    from pathlib import Path

    from smalltobig.llm.client import ChatMessage

SENTINEL = "SENTINEL-api-Marisol-55120"
TURNS = [
    {"speaker": "partner", "text": "Hi, first time here?"},
    {"speaker": "user", "text": f"Honestly I almost didn't come, {SENTINEL}."},
    {"speaker": "partner", "text": "Same. I keep meaning to start running again."},
    {"speaker": "user", "text": "What keeps getting in the way of the running?"},
]


class Fake:
    def __init__(self, *a: object, **k: object) -> None:
        pass

    def __enter__(self) -> Fake:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def health(self) -> bool:
        return True

    def chat(self, messages: list[ChatMessage], *, max_tokens: int = 256,
             temperature: float = 0.0) -> str:
        if messages[0]["content"] == htmsw_judge.SYSTEM_PROMPT:
            return json.dumps([
                {"item": 1, "passed": True, "quote": f"I almost didn't come, {SENTINEL}."},
                {"item": 2, "passed": True,
                 "quote": "What keeps getting in the way of the running?",
                 "partner_quote": "I keep meaning to start running again."},
            ])
        return json.dumps([{"item": 1, "passed": True, "quote": SENTINEL}])


class Down(Fake):
    def chat(self, *a: object, **k: object) -> str:
        raise httpx.ConnectError("refused")


def _app(tmp_path: Path, profile: str = "abstracted") -> tuple[TestClient, Settings]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, data_dir=tmp_path / "data", privacy_profile=profile
    )
    return TestClient(create_app(settings)), settings


@pytest.fixture(autouse=True)
def fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(htmsw_api, "_client", lambda _s: Fake())


def test_framework_export_is_complete_and_has_no_actor_secrets(tmp_path: Path) -> None:
    client, _ = _app(tmp_path)
    body = client.get("/api/htmsw/framework").json()
    assert [s["id"] for s in body["steps"]] == ["step_1", "step_2", "step_3", "step_4"]
    assert body["steps"][1]["aliases"]["be_better"] == "buildOn"
    assert {d["aliases"]["be_better"] for d in body["domains"]} == {
        "networking", "acquaintance", "collaborator", "givingBack"}
    assert len(body["rubric"]) == 4 and body["progress"]["real_weight"] == 3
    assert "private_instructions" not in json.dumps(body)
    assert "partners" not in body


def test_revision_is_stable_and_tracks_content() -> None:
    fw = load_framework(Settings(_env_file=None).framework_dir)  # type: ignore[call-arg]
    assert export(fw)["revision"] == export(fw)["revision"]
    changed = fw.model_copy(update={"steps": fw.steps[:3]})
    assert export(changed)["revision"] != export(fw)["revision"]


def test_judge_verifies_records_and_reports_profile(tmp_path: Path) -> None:
    client, settings = _app(tmp_path)
    r = client.post("/api/htmsw/judge",
                    json={"turns": TURNS, "domain_id": "cold_networking", "client": "be-better"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [v["passed"] for v in body["verdicts"]] == [True, True, False, False]
    assert body["verdicts"][1]["partner_quote"] == "I keep meaning to start running again."
    assert body["recorded"] and body["privacy_profile"] == "abstracted"
    progress = client.get("/api/htmsw/progress").json()
    assert progress["outcomes"] == 4


def test_judge_can_skip_recording(tmp_path: Path) -> None:
    client, settings = _app(tmp_path)
    r = client.post("/api/htmsw/judge",
                    json={"turns": TURNS, "domain_id": "cold_networking", "record": False})
    assert r.status_code == 200 and r.json()["recorded"] is False
    assert not settings.record_db_path.exists()


def test_api_cannot_bypass_the_abstracted_profile(tmp_path: Path) -> None:
    client, settings = _app(tmp_path)
    client.post("/api/htmsw/judge", json={"turns": TURNS, "domain_id": "cold_networking"})
    client.post("/api/htmsw/debrief", json={"account": f"I told her {SENTINEL}.",
                                             "domain_id": "giving_back", "consent": "obtained"})
    for path in settings.data_dir.glob("*.db"):
        conn = sqlite3.connect(path)
        try:
            for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                for row in conn.execute(f"SELECT * FROM {table}"):  # noqa: S608
                    assert all(SENTINEL not in str(v) for v in row), (path.name, table)
        finally:
            conn.close()


def test_full_profile_keeps_api_sessions(tmp_path: Path) -> None:
    client, settings = _app(tmp_path, "full")
    client.post("/api/htmsw/judge",
                json={"turns": TURNS, "domain_id": "cold_networking", "client": "be-better"})
    conn = sqlite3.connect(settings.record_db_path)
    try:
        partner, turns = conn.execute("SELECT partner_id, turns_json FROM sessions").fetchone()
    finally:
        conn.close()
    assert partner == "be-better" and SENTINEL in turns


@pytest.mark.parametrize(
    "payload",
    [
        {"turns": TURNS, "domain_id": "nowhere"},
        {"turns": TURNS[:1], "domain_id": "cold_networking"},
        {"turns": [TURNS[0], TURNS[2]], "domain_id": "cold_networking"},
        {"turns": [{"speaker": "narrator", "text": "x"}] * 2, "domain_id": "cold_networking"},
    ],
)
def test_judge_rejects_bad_requests(tmp_path: Path, payload: dict[str, object]) -> None:
    client, _ = _app(tmp_path)
    assert client.post("/api/htmsw/judge", json=payload).status_code == 422


def test_model_down_is_a_503_not_a_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(htmsw_api, "_client", lambda _s: Down())
    client, settings = _app(tmp_path)
    r = client.post("/api/htmsw/judge", json={"turns": TURNS, "domain_id": "cold_networking"})
    assert r.status_code == 503 and r.json()["error"] == "model_unavailable"
    assert not settings.record_db_path.exists()


def test_debrief_validates_consent(tmp_path: Path) -> None:
    client, _ = _app(tmp_path)
    r = client.post("/api/htmsw/debrief",
                    json={"account": "x", "domain_id": "giving_back", "consent": "maybe"})
    assert r.status_code == 422
