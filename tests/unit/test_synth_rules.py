from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from smalltobig.models.claim import Claim, ClaimStatus, ClaimType
from smalltobig.synth.rules import draft_rule_from_cluster

if TYPE_CHECKING:
    from smalltobig.llm.client import ChatMessage


class _FakeClient:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def health(self) -> bool:
        return True

    def chat(
        self, messages: list[ChatMessage], *, max_tokens: int = 256, temperature: float = 0.0
    ) -> str:
        return self._reply


def _claim(verbatim: str, paraphrase: str) -> Claim:
    return Claim(
        id="clm_1",
        source_id="src_1",
        chunk_index=0,
        verbatim=verbatim,
        paraphrase=paraphrase,
        claim_type=ClaimType.EMPIRICAL_FINDING,
        status=ClaimStatus.ACCEPTED,
        start=0,
        end=len(verbatim),
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
    )


VALID_REPLY = (
    '{"name": "Ask follow-up questions", '
    '"imperative": "Ask about what they just said.", '
    '"rationale": "Follow-ups signal responsiveness.", '
    '"when_to_apply": "Past the opening two turns.", '
    '"antipattern": "Changing the subject.", '
    '"evidence_tier": "A", '
    '"rubric": [{"id": "asked_followup", "check": "Did you ask a follow-up?"}]}'
)


def test_drafts_a_rule_from_a_clean_reply() -> None:
    claims = [_claim("Ask follow-up questions.", "Follow up.")]
    rule = draft_rule_from_cluster(_FakeClient(VALID_REPLY), claims)
    assert rule is not None
    assert rule.name == "Ask follow-up questions"
    assert rule.evidence_tier == "A"
    assert rule.rubric[0].check.endswith("?")


def test_tolerates_markdown_fences() -> None:
    fenced = f"```json\n{VALID_REPLY}\n```"
    claims = [_claim("Ask follow-up questions.", "Follow up.")]
    rule = draft_rule_from_cluster(_FakeClient(fenced), claims)
    assert rule is not None


def test_returns_none_for_invalid_json() -> None:
    claims = [_claim("X.", "Y.")]
    assert draft_rule_from_cluster(_FakeClient("not json"), claims) is None


def test_returns_none_for_missing_required_field() -> None:
    incomplete = '{"name": "Only a name"}'
    claims = [_claim("X.", "Y.")]
    assert draft_rule_from_cluster(_FakeClient(incomplete), claims) is None


def test_returns_none_for_invalid_evidence_tier() -> None:
    bad_tier = VALID_REPLY.replace('"evidence_tier": "A"', '"evidence_tier": "Z"')
    claims = [_claim("X.", "Y.")]
    assert draft_rule_from_cluster(_FakeClient(bad_tier), claims) is None
