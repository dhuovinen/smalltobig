"""HTMSW rehearsal (IMPLEMENTATION.md Phase 3): actor isolation, judge isolation,
and the verify-then-check pipeline that turns a judge reply into verdicts."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from smalltobig.config import Settings
from smalltobig.framework.loader import load_framework
from smalltobig.models.session import Turn
from smalltobig.practice import htmsw_judge, htmsw_roleplay
from smalltobig.web.app import create_app
from smalltobig.web.routes import htmsw as htmsw_routes

if TYPE_CHECKING:
    from pathlib import Path

    from smalltobig.framework.loader import Framework
    from smalltobig.llm.client import ChatMessage

# The Sarah worked example (docs/REQUIREMENTS.md FR-41), abridged.
def _p(text: str) -> Turn:
    return Turn(speaker="partner", text=text)


def _u(text: str) -> Turn:
    return Turn(speaker="user", text=text)


SARAH = [
    _p("Hi, I don't think we've met. Is this your first time at one of these?"),
    _u("Actually, yeah. I'll be honest, I almost didn't come. "
       "These things make me feel like I'm working the room."),
    _p("Ha, I get that. I almost bailed tonight too. "
       "I've been trying to get back into running but it keeps falling off."),
    _u("What gets in the way of the running, do you think?"),
    _p("Honestly I never protect the time on my calendar for it."),
    _u("I hear you on things falling off the list. "
       "For me it's time with my kids before that window closes."),
    _p("That's a good instinct. A lot of people wait too long."),
    _u("If you ever want someone to check in on the running, "
       "I'm happy to be a witness. No pressure."),
]

GOOD_REPLY = json.dumps([
    {"item": 1, "passed": True, "quote": "I'll be honest, I almost didn't come.",
     "partner_quote": ""},
    {"item": 2, "passed": True, "quote": "What gets in the way of the running, do you think?",
     "partner_quote": "I've been trying to get back into running but it keeps falling off."},
    {"item": 3, "passed": True,
     "quote": "For me it's time with my kids before that window closes.",
     "partner_quote": "Honestly I never protect the time on my calendar for it."},
    {"item": 4, "passed": True, "quote": "I'm happy to be a witness.", "partner_quote": ""},
])


class FakeClient:
    """Records every chat call; actor calls get a canned line, judge calls `judge_reply`."""

    def __init__(self, calls: list[list[ChatMessage]], judge_reply: str = GOOD_REPLY) -> None:
        self.calls = calls
        self.judge_reply = judge_reply

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def health(self) -> bool:
        return True

    def chat(self, messages: list[ChatMessage], *, max_tokens: int = 256,
             temperature: float = 0.0) -> str:
        self.calls.append(messages)
        if messages[0]["content"] == htmsw_judge.SYSTEM_PROMPT:
            return self.judge_reply
        return "Oh nice, tell me more."


@pytest.fixture(scope="module")
def fw() -> Framework:
    return load_framework(Settings(_env_file=None).framework_dir)  # type: ignore[call-arg]


def _forbidden_for_actor(fw: Framework) -> list[str]:
    terms = ["HTMSW", "rubric", "step_1", "step_2", "step_3", "step_4"]
    for step in fw.steps:
        terms += [step.name, step.definition, step.coaching, step.antipattern]
    for item in fw.rubric:
        terms += [item.id, item.check]
    return terms


# ------------------------------------------------------------------ actor isolation


def test_partner_data_never_names_the_framework(fw: Framework) -> None:
    for partner in fw.partners:
        blob = " ".join(str(v) for v in partner.model_dump().values()).lower()
        for term in _forbidden_for_actor(fw):
            assert term.lower() not in blob, f"{partner.id} mentions {term!r}"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]


@pytest.fixture
def web(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, list[Any]]:
    calls: list[list[ChatMessage]] = []
    monkeypatch.setattr(htmsw_routes, "_client", lambda _s: FakeClient(calls))
    return TestClient(create_app(settings)), calls


def _rehearse(client: TestClient, partner_id: str, lines: list[str]) -> str:
    """Drive start -> turns -> end through the real routes; return the final page."""
    page = client.post("/htmsw/rehearse/start", data={"partner_id": partner_id})
    assert page.status_code == 200
    turns_json = _hidden_turns(page.text)
    for line in lines:
        page = client.post(
            "/htmsw/rehearse/turn",
            data={"partner_id": partner_id, "turns_json": turns_json, "line": line},
        )
        assert page.status_code == 200
        turns_json = _hidden_turns(page.text)
    end = client.post(
        "/htmsw/rehearse/end", data={"partner_id": partner_id, "turns_json": turns_json}
    )
    assert end.status_code == 200
    return end.text


def _hidden_turns(html: str) -> str:
    import html as html_lib
    marker = 'name="turns_json" value="'
    start = html.index(marker) + len(marker)
    return html_lib.unescape(html[start:html.index('"', start)])


@pytest.mark.parametrize("partner_id", ["sarah", "mike"])
def test_no_actor_payload_contains_rubric_or_step_text(
    web: tuple[TestClient, list[Any]], fw: Framework, partner_id: str
) -> None:
    # FR-42, checked over the real outbound payloads, not the template.
    client, calls = web
    _rehearse(client, partner_id, [
        "I'll be honest, I almost didn't come tonight.",
        "What pulled you into that?",
        "That connects with something for me too.",
    ])
    actor_calls = [c for c in calls if c[0]["content"] != htmsw_judge.SYSTEM_PROMPT]
    assert len(actor_calls) == 3
    forbidden = _forbidden_for_actor(fw)
    for messages in actor_calls:
        for message in messages:
            text = message["content"].lower()
            for term in forbidden:
                assert term.lower() not in text, f"actor saw {term!r}"


def test_judge_never_sees_the_partner_persona(
    web: tuple[TestClient, list[Any]], fw: Framework
) -> None:
    # FR-43
    client, calls = web
    _rehearse(client, "sarah", ["I'll be honest, I almost didn't come."])
    judge_calls = [c for c in calls if c[0]["content"] == htmsw_judge.SYSTEM_PROMPT]
    assert len(judge_calls) == 1
    sarah = fw.partner("sarah")
    payload = " ".join(m["content"] for m in judge_calls[0])
    for secret in (sarah.private_instructions, sarah.hidden_interest, sarah.setting,
                   sarah.warmth, sarah.verbosity):
        assert secret not in payload


# ---------------------------------------------------------------------- the judge


def test_sarah_rehearsal_yields_four_verified_verdicts(fw: Framework) -> None:
    # "Done when": four verdicts, each with a span that appears in the transcript.
    verdicts = htmsw_judge.judge(FakeClient([]), fw, SARAH)
    assert [v.step_id for v in verdicts] == ["step_1", "step_2", "step_3", "step_4"]
    user_text = [t.text for t in SARAH if t.speaker == "user"]
    partner_text = [t.text for t in SARAH if t.speaker == "partner"]
    for v in verdicts:
        assert v.passed, (v.rubric_id, v.reason)
        assert v.quote and any(v.quote in line for line in user_text)
        if v.partner_quote:
            assert any(v.partner_quote in line for line in partner_text)


def _one(fw: Framework, item: int, **fields: Any) -> htmsw_judge.StepVerdict:
    entry = {"item": item, "passed": True, "quote": "", "partner_quote": "", **fields}
    reply = json.dumps([entry])
    return htmsw_judge.judge(FakeClient([], reply), fw, SARAH)[item - 1]


def test_invented_quote_fails(fw: Framework) -> None:
    v = _one(fw, 1, quote="I am so nervous about meeting new people")
    assert not v.passed and "not in any of your lines" in (v.reason or "")


def test_paraphrased_quote_fails(fw: Framework) -> None:
    v = _one(fw, 1, quote="I'll be honest, I nearly didn't come.")
    assert not v.passed


def test_build_on_without_partner_quote_fails(fw: Framework) -> None:
    # The DECISIONS #16 false positive: a question alone is not a build-on.
    v = _one(fw, 2, quote="What gets in the way of the running, do you think?")
    assert not v.passed and "partner" in (v.reason or "")


def test_partner_quote_must_come_before_the_user_line(fw: Framework) -> None:
    v = _one(fw, 2, quote="What gets in the way of the running, do you think?",
             partner_quote="Honestly I never protect the time on my calendar for it.")
    assert not v.passed


def test_disclosure_after_a_question_fails(fw: Framework) -> None:
    v = _one(fw, 1, quote="For me it's time with my kids before that window closes.")
    assert not v.passed and "question before" in (v.reason or "")


def test_ask_too_early_fails(fw: Framework) -> None:
    v = _one(fw, 4, quote="I'll be honest, I almost didn't come.")
    assert not v.passed and "rounds" in (v.reason or "")


def test_judge_no_is_a_miss_with_a_reason(fw: Framework) -> None:
    v = _one(fw, 3, passed=False)
    assert not v.passed and v.quote is None and v.reason


@pytest.mark.parametrize("reply", ["", "not json", "[1, 2", '{"item": 1}', "[[]]"])
def test_malformed_judge_reply_gives_four_misses(fw: Framework, reply: str) -> None:
    verdicts = htmsw_judge.judge(FakeClient([], reply), fw, SARAH)
    assert len(verdicts) == 4 and not any(v.passed for v in verdicts)


def test_thinking_blocks_are_ignored(fw: Framework) -> None:
    reply = "<think>maybe [1, 2] or not</think>" + GOOD_REPLY
    verdicts = htmsw_judge.judge(FakeClient([], reply), fw, SARAH)
    assert all(v.passed for v in verdicts)


def test_no_numeric_scoring_in_verdicts() -> None:
    # FR-46: boolean plus span only.
    fields = htmsw_judge.StepVerdict.model_fields
    numeric = [n for n, f in fields.items() if f.annotation in (int, float)]
    assert not numeric


# ----------------------------------------------------------------------- the routes


def test_partners_cover_their_domains(fw: Framework) -> None:
    assert [p.id for p in htmsw_roleplay.partners_for(fw, "cold_networking")] == ["sarah"]
    assert [p.id for p in htmsw_roleplay.partners_for(fw, "potential_collaborator")] == ["mike"]
    assert htmsw_roleplay.partners_for(fw, "casual_acquaintance") == []


def test_result_page_shows_verdicts_and_keeps_no_transcript(
    web: tuple[TestClient, list[Any]], settings: Settings
) -> None:
    # Default profile is abstracted: scoring records four integer outcomes, and the
    # transcript reaches no database file (DECISIONS #24, FR-51).
    client, _ = web
    sentinel = "SENTINEL-rehearsal-line-9917"
    page = _rehearse(client, "sarah", [sentinel])
    for name in ("Initial disclosure", "Build-on question", "Connecting micro-disclosure",
                 "Earned ask"):
        assert name in page
    assert "the transcript was not stored" in page
    for path in settings.data_dir.glob("*.db"):
        conn = sqlite3.connect(path)
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                for row in conn.execute(f"SELECT * FROM {table}"):  # noqa: S608
                    assert all(sentinel not in str(v) for v in row), (path.name, table)
        finally:
            conn.close()


def test_unknown_partner_is_404(web: tuple[TestClient, list[Any]]) -> None:
    client, _ = web
    assert client.post("/htmsw/rehearse/start", data={"partner_id": "nobody"}).status_code == 404


def test_tampered_transcript_is_rejected(web: tuple[TestClient, list[Any]]) -> None:
    client, _ = web
    for bad in ("not json", "[]", '[{"speaker": "narrator", "text": "x"}]'):
        r = client.post("/htmsw/rehearse/end", data={"partner_id": "sarah", "turns_json": bad})
        assert r.status_code == 400


def test_prep_card_offers_a_rehearsal(settings: Settings) -> None:
    client = TestClient(create_app(settings))
    client.post("/htmsw/profile", data={"has_kids": "no", "caregiving": "no",
                                        "primary_focus": "professional"})
    card = client.post("/htmsw/prep", data={"domain_id": "potential_collaborator"})
    assert "Rehearse this with Mike" in card.text
    card = client.post("/htmsw/prep", data={"domain_id": "casual_acquaintance"})
    assert "Rehearse this" not in card.text


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("*glances at it with a half-smile* You might want to come back.",
         "You might want to come back."),
        ("Oh god, no. *laughs softly* What's your angle?", "Oh god, no. What's your angle?"),
        ("I *do* love a good coffee chat", "I do love a good coffee chat"),
        ("Fine [sips drink]", "Fine"),
        ("Ok (sorry)", "Ok (sorry)"),
        ("No stage directions here.", "No stage directions here."),
        ("*sighs heavily*", "*sighs heavily*"),  # never return an empty line
    ],
)
def test_clean_strips_stage_directions(raw: str, cleaned: str) -> None:
    # DECISIONS #25: the actor adds these despite the prompt.
    assert htmsw_roleplay.clean(raw) == cleaned


def test_judge_prompt_shows_a_filled_partner_quote() -> None:
    # DECISIONS #25: an empty-only example left partner_quote blank in live runs.
    assert '"partner_quote": "exact words from the earlier partner line' in (
        htmsw_judge.SYSTEM_PROMPT
    )


def test_judge_yes_without_a_quote_is_a_miss(fw: Framework) -> None:
    v = _one(fw, 4, quote="")
    assert not v.passed and "quoted nothing" in (v.reason or "")
