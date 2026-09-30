from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from smalltobig import cli
from smalltobig.config import Settings
from smalltobig.web.app import create_app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data", repo_root=tmp_path / "repo")  # type: ignore[call-arg]


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def test_home_offers_starter_rules_only_while_there_are_no_rules(client: TestClient) -> None:
    assert "Load starter rules" in client.get("/home").text

    client.post("/seed")

    assert "Load starter rules" not in client.get("/home").text


def test_loading_starter_rules_redirects_to_the_rules_list(client: TestClient) -> None:
    response = client.post("/seed", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/rules?seeded=15"


def test_the_rules_list_explains_what_was_loaded_and_flags_each_rule(client: TestClient) -> None:
    client.post("/seed")
    page = client.get("/rules?seeded=15").text
    assert "Loaded 15 starter rules" in page
    assert page.count("unverified</span>") == 15


def test_a_starter_rule_page_says_it_is_unverified_and_shows_its_basis(
    client: TestClient,
) -> None:
    client.post("/seed")
    page = client.get("/rules/ask-follow-up-questions").text
    assert "Unverified starter rule" in page
    assert "What the sources are reported to say" in page
    assert "It Doesn&#39;t Hurt to Ask" in page


def test_after_loading_the_next_move_is_to_review_not_to_add_a_source(
    client: TestClient,
) -> None:
    client.post("/seed")
    page = client.get("/home").text
    assert "candidate rules" in page
    assert "Feed it something to read" not in page


def test_the_seeded_disagreements_appear_for_arbitration(client: TestClient) -> None:
    client.post("/seed")
    assert "balance-the-airtime" in client.get("/conflicts").text


def test_stb_seed_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STB_DATA_DIR", str(tmp_path))
    first = CliRunner().invoke(cli.main, ["seed"])
    assert first.exit_code == 0
    assert "15 rule(s) added" in first.output

    second = CliRunner().invoke(cli.main, ["seed"])
    assert "0 rule(s) added, 15 already present" in second.output
