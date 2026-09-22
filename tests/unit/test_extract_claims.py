from __future__ import annotations

from typing import TYPE_CHECKING

from smalltobig.extract.claims import extract_claims_from_chunk

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


def test_parses_a_clean_json_array() -> None:
    reply = (
        '[{"verbatim": "Ask follow-up questions.", "paraphrase": "Follow up.", '
        '"claim_type": "prescriptive"}]'
    )
    claims = extract_claims_from_chunk(_FakeClient(reply), "some chunk")
    assert len(claims) == 1
    assert claims[0].verbatim == "Ask follow-up questions."
    assert claims[0].claim_type == "prescriptive"


def test_tolerates_markdown_fences_and_surrounding_prose() -> None:
    reply = (
        "Here are the claims:\n```json\n"
        '[{"verbatim": "Be present.", "paraphrase": "Presence matters.", '
        '"claim_type": "descriptive"}]\n```\nHope that helps!'
    )
    claims = extract_claims_from_chunk(_FakeClient(reply), "some chunk")
    assert len(claims) == 1
    assert claims[0].verbatim == "Be present."


def test_empty_array_yields_no_claims() -> None:
    assert extract_claims_from_chunk(_FakeClient("[]"), "some chunk") == []


def test_invalid_json_yields_no_claims_rather_than_raising() -> None:
    assert extract_claims_from_chunk(_FakeClient("not json at all"), "some chunk") == []


def test_skips_items_missing_required_fields_but_keeps_valid_ones() -> None:
    reply = (
        "["
        '{"verbatim": "Good one.", "paraphrase": "P.", "claim_type": "anecdote"},'
        '{"paraphrase": "Missing verbatim."}'
        "]"
    )
    claims = extract_claims_from_chunk(_FakeClient(reply), "some chunk")
    assert len(claims) == 1
    assert claims[0].verbatim == "Good one."


def test_skips_items_with_an_invalid_claim_type() -> None:
    reply = '[{"verbatim": "X.", "paraphrase": "Y.", "claim_type": "opinion"}]'
    assert extract_claims_from_chunk(_FakeClient(reply), "some chunk") == []
