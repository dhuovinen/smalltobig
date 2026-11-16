from __future__ import annotations

from smalltobig.extract.verify import verify_claim


def test_accepts_an_exact_substring() -> None:
    source = "Ask follow-up questions, not new ones."
    result = verify_claim(source, "follow-up questions")
    assert result.accepted
    assert result.start == source.index("follow-up questions")
    assert result.end == result.start + len("follow-up questions")
    assert result.reason is None


def test_rejects_a_span_not_present() -> None:
    result = verify_claim("Ask follow-up questions.", "boomerask your own answer")
    assert not result.accepted
    assert result.start is None
    assert result.end is None
    assert result.reason == "span not found in source"


def test_rejects_a_paraphrased_near_miss() -> None:
    # A claim that reorders or rewords the source, rather than quoting it,
    # is exactly what the gate exists to catch (docs/DECISIONS.md #3).
    source = "Follow-up questions signal responsiveness."
    result = verify_claim(source, "Questions that follow up signal responsiveness.")
    assert not result.accepted


def test_rejects_empty_verbatim() -> None:
    result = verify_claim("Any source text at all.", "")
    assert not result.accepted
    assert result.reason == "empty verbatim span"


def test_finds_the_first_occurrence() -> None:
    source = "repeat repeat repeat"
    result = verify_claim(source, "repeat")
    assert result.start == 0
