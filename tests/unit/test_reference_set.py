"""The HTMSW judge reference set (evals/htmsw_reference.yaml) and its runner."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from smalltobig.config import Settings
from smalltobig.framework.loader import load_framework
from smalltobig.practice import reference_set

if TYPE_CHECKING:
    from smalltobig.framework.loader import Framework
    from smalltobig.llm.client import ChatMessage


@pytest.fixture(scope="module")
def fw() -> Framework:
    return load_framework(Settings(_env_file=None).framework_dir)  # type: ignore[call-arg]


@pytest.fixture(scope="module")
def refset() -> reference_set.ReferenceSet:
    return reference_set.load()


def test_reference_set_size_meets_the_focus_plan(refset: reference_set.ReferenceSet) -> None:
    # docs/FOCUS.md Step 0: 10+ Sarah rehearsals and 6+ debriefs.
    assert len(refset.rehearsals) >= 10
    assert len(refset.debriefs) >= 6
    # Both outcomes are represented for every step, or agreement means little.
    for cases in (refset.rehearsals, refset.debriefs):
        for step in range(4):
            assert {c.expected[step] for c in cases} == {True, False}, step + 1


def test_rehearsals_open_with_sarahs_line_and_alternate(
    fw: Framework, refset: reference_set.ReferenceSet
) -> None:
    opening = fw.partner("sarah").opening_line.strip()
    for case in refset.rehearsals:
        assert case.turns[0].speaker == "partner" and case.turns[0].text == opening, case.id
        speakers = [t.speaker for t in case.turns]
        assert all(a != b for a, b in zip(speakers, speakers[1:], strict=False)), case.id


def test_labels_respect_the_structural_rules(refset: reference_set.ReferenceSet) -> None:
    # Step 1 cannot pass when the user's first line is a question (no_user_question_before),
    # and step 4 cannot pass without two exchanges before the user's last line.
    for case in refset.rehearsals:
        user_lines = [t.text for t in case.turns if t.speaker == "user"]
        if case.expected[0]:
            assert "?" not in user_lines[0], case.id
        if case.expected[3]:
            assert len(user_lines) >= 3, case.id


def test_duplicate_ids_are_refused(tmp_path: object) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        reference_set.ReferenceSet.model_validate({
            "version": 1,
            "rehearsals": [{"id": "a", "note": "n", "expected": [True] * 4,
                            "turns": [{"partner": "hi"}, {"user": "hello"}]}],
            "debriefs": [{"id": "a", "note": "n", "expected": [True] * 4, "account": "x"}],
        })


class AlwaysNo:
    """A judge that passes nothing: agreement equals the share of 'not yet' labels."""

    def chat(self, messages: list[ChatMessage], *, max_tokens: int = 256,
             temperature: float = 0.0) -> str:
        return json.dumps([{"item": i, "passed": False, "quote": ""} for i in range(1, 5)])

    def health(self) -> bool:
        return True


def test_runner_counts_agreement_and_error_direction(
    fw: Framework, refset: reference_set.ReferenceSet
) -> None:
    report = reference_set.run(AlwaysNo(), fw, refset)  # type: ignore[arg-type]
    assert len(report.results) == len(refset.rehearsals) + len(refset.debriefs)
    for kind, cases in (("rehearsal", refset.rehearsals), ("debrief", refset.debriefs)):
        for step in range(1, 5):
            negatives = sum(not c.expected[step - 1] for c in cases)
            assert report.agreement(kind, step) == (negatives, len(cases))  # type: ignore[arg-type]
            assert report.errors(kind, step) == (0, len(cases) - negatives)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- live

# Baseline from the first live run (DECISIONS #28). A judge, prompt or model change
# must not take any step below these. Raise them when a change improves a step.
# Qwen-AgentWorld-35B-A3B-oQ4, thinking off, 2026-11-19: the lowest score per step
# over five runs. Rehearsal steps 2 and 3 vary by one case between runs.
BASELINE = {
    "rehearsal": {1: 10, 2: 9, 3: 8, 4: 9},
    "debrief": {1: 6, 2: 6, 3: 6, 4: 4},
}


@pytest.mark.mlx
def test_live_model_meets_the_reference_baseline(
    fw: Framework, refset: reference_set.ReferenceSet
) -> None:
    from smalltobig.llm.openai_compat import OpenAICompatClient

    settings = Settings()  # reads .env: the configured model server
    with OpenAICompatClient(settings.llm_base_url, **settings.llm_options()) as client:
        if not client.health():
            pytest.skip("model server not reachable")
        report = reference_set.run(client, fw, refset)
    below = {
        (kind, step): report.agreement(kind, step)  # type: ignore[arg-type]
        for kind, floors in BASELINE.items() for step, floor in floors.items()
        if report.agreement(kind, step)[0] < floor  # type: ignore[arg-type]
    }
    assert not below, below

