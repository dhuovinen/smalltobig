"""record/: counters and levels (FR-54), debrief extraction (FR-53), CLI surfaces."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from smalltobig.cli import main
from smalltobig.config import Settings
from smalltobig.framework.loader import load_framework
from smalltobig.practice import htmsw_debrief
from smalltobig.record.counters import StepCounter, counters
from smalltobig.record.models import Outcome

if TYPE_CHECKING:
    from pathlib import Path

    from smalltobig.framework.loader import Framework
    from smalltobig.llm.client import ChatMessage


@pytest.fixture(scope="module")
def fw() -> Framework:
    return load_framework(Settings(_env_file=None).framework_dir)  # type: ignore[call-arg]


def _o(source: str, passed: bool, step: int = 2, domain: str = "cold_networking") -> Outcome:
    return Outcome(step_order=step, domain_id=domain, source=source, passed=passed, at=0)  # type: ignore[arg-type]


def _cell(fw: Framework, outcomes: list[Outcome], step: int = 2,
          domain: str = "cold_networking") -> StepCounter:
    return next(c for c in counters(fw, outcomes)
                if c.step_order == step and c.domain_id == domain)


def test_every_step_domain_pair_has_a_counter(fw: Framework) -> None:
    table = counters(fw, [])
    assert len(table) == len(fw.steps) * len(fw.domains)
    assert {c.level_id for c in table} == {"not_started"}


def test_counters_accumulate_across_sessions(fw: Framework) -> None:
    outcomes = [_o("rehearsal", True), _o("rehearsal", False), _o("rehearsal", True)]
    c = _cell(fw, outcomes)
    assert (c.rehearsal_attempts, c.rehearsal_successes) == (3, 2)
    assert c.weighted_successes == 2


def test_real_conversations_weigh_three_times(fw: Framework) -> None:
    c = _cell(fw, [_o("real", True)])
    assert c.weighted_successes == fw.progress.real_weight == 3
    assert c.level_id == "practising"


def test_rehearsals_alone_never_reach_the_top_level(fw: Framework) -> None:
    # FR-54: the app must not certify you as good at talking to a language model.
    c = _cell(fw, [_o("rehearsal", True)] * 100)
    assert c.weighted_successes == 100
    assert c.level_id != "confident"


def test_confident_needs_real_successes(fw: Framework) -> None:
    # Two real successes (6 weighted) plus three rehearsals (3) reaches 9.
    c = _cell(fw, [_o("real", True)] * 2 + [_o("rehearsal", True)] * 3)
    assert (c.real_successes, c.weighted_successes) == (2, 9)
    assert c.level_id == "confident"
    # The same weight from one real success plus rehearsals does not.
    c = _cell(fw, [_o("real", True)] + [_o("rehearsal", True)] * 6)
    assert c.weighted_successes == 9 and c.level_id == "practising"


def test_outcomes_are_kept_per_domain(fw: Framework) -> None:
    outcomes = [_o("real", True, domain="giving_back")]
    assert _cell(fw, outcomes, domain="giving_back").real_successes == 1
    assert _cell(fw, outcomes, domain="cold_networking").real_successes == 0


# ------------------------------------------------------------------------- debrief

ACCOUNT = (
    "At the mixer I admitted I almost didn't come because these things make me anxious. "
    "She said she's been trying to run again, so I asked what keeps getting in the way."
)


class Canned:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.messages: list[ChatMessage] = []

    def health(self) -> bool:
        return True

    def chat(self, messages: list[ChatMessage], *, max_tokens: int = 256,
             temperature: float = 0.0) -> str:
        self.messages = messages
        return self.reply


def test_debrief_keeps_only_verified_quotes(fw: Framework) -> None:
    reply = json.dumps([
        {"item": 1, "passed": True, "quote": "I admitted I almost didn't come"},
        {"item": 2, "passed": True, "quote": "I asked what keeps getting in the way"},
        {"item": 3, "passed": True, "quote": "I told her about my kids"},  # not in account
        {"item": 4, "passed": False, "quote": ""},
    ])
    verdicts, _, raw = htmsw_debrief.extract(Canned(reply), fw, ACCOUNT)
    assert [v.passed for v in verdicts] == [True, True, False, False]
    assert "not in your account" in (verdicts[2].reason or "")
    assert raw == reply


def test_debrief_walks_checks_in_order_and_never_sees_personas(fw: Framework) -> None:
    client = Canned("[]")
    htmsw_debrief.extract(client, fw, ACCOUNT)
    payload = " ".join(m["content"] for m in client.messages)
    assert "one at a time" in payload
    for partner in fw.partners:
        assert partner.private_instructions not in payload


@pytest.mark.parametrize("reply", ["", "nonsense", "[{]"])
def test_debrief_survives_malformed_replies(fw: Framework, reply: str) -> None:
    verdicts, _, _ = htmsw_debrief.extract(Canned(reply), fw, ACCOUNT)
    assert len(verdicts) == 4 and not any(v.passed for v in verdicts)


# ----------------------------------------------------------------------------- CLI


class CannedClient(Canned):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(json.dumps([
            {"item": 1, "passed": True, "quote": "I admitted I almost didn't come"}]))

    def __enter__(self) -> CannedClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import smalltobig.llm.openai_compat as compat

    monkeypatch.setattr(compat, "OpenAICompatClient", CannedClient)
    monkeypatch.setenv("STB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("STB_PRIVACY_PROFILE", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path / "data"


def test_cli_debrief_progress_purge(cli_env: Path) -> None:
    runner = CliRunner()
    out = runner.invoke(main, ["debrief", "--domain", "cold_networking"], input=ACCOUNT)
    assert out.exit_code == 0, out.output
    assert "1. Initial disclosure: yes" in out.output
    assert "four yes/no outcomes only" in out.output
    progress = runner.invoke(main, ["progress"])
    assert progress.exit_code == 0, progress.output
    assert "Privacy profile: abstracted" in progress.output
    assert "real 1/1" in progress.output
    purged = runner.invoke(main, ["purge", "--yes"])
    assert purged.exit_code == 0 and "Purged" in purged.output
    assert not (cli_env / "htmsw-abstracted.db").exists()


def test_cli_debrief_rejects_empty_account(cli_env: Path) -> None:
    out = CliRunner().invoke(main, ["debrief", "--domain", "cold_networking"], input="  ")
    assert out.exit_code == 2


def test_record_timestamps_are_unix_seconds(fw: Framework) -> None:
    from smalltobig.practice.htmsw_judge import StepVerdict
    from smalltobig.record.models import SessionRecord
    from smalltobig.record.projection import project

    at = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
    record = SessionRecord(
        source="real", domain_id="giving_back", created_at=at,
        verdicts=(StepVerdict(step_id="step_4", rubric_id="ask_was_earned", check="c",
                              passed=True, quote="q"),),
    )
    (o,) = project(fw, record)
    assert o.at == int(at.timestamp()) and o.step_order == 4


def test_debrief_yes_without_a_quote_is_a_miss_with_an_honest_reason(fw: Framework) -> None:
    # Live, the model answered {"item": 4, "passed": true, "quote": ""}.
    reply = json.dumps([{"item": 4, "passed": True, "quote": ""}])
    verdicts, _, _ = htmsw_debrief.extract(Canned(reply), fw, ACCOUNT)
    assert not verdicts[3].passed
    assert "quoted nothing" in (verdicts[3].reason or "")
