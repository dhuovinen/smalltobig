"""prep/compose.py: every (cluster x domain) yields a complete four-step card."""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

import pytest

from smalltobig.config import Settings
from smalltobig.framework.loader import load_framework
from smalltobig.prep.compose import compose, is_thin, render_text

if TYPE_CHECKING:
    from smalltobig.framework.loader import Framework

RICH = "Runs operations at a logistics startup downtown, moved here from Chicago two years ago"


@pytest.fixture(scope="module")
def fw() -> Framework:
    return load_framework(Settings(_env_file=None).framework_dir)  # type: ignore[call-arg]


def test_every_pair_returns_four_complete_steps(fw: Framework) -> None:
    for cluster, domain in itertools.product(fw.clusters, fw.domains):
        for notes in ("", RICH):
            card = compose(fw, cluster.id, domain.id, target_notes=notes)
            assert [s.id for s in card.steps] == ["step_1", "step_2", "step_3", "step_4"]
            assert card.complete, (cluster.id, domain.id)


def test_declared_gap_surfaces_on_the_card(fw: Framework) -> None:
    card = compose(fw, "professional_independent", "potential_collaborator")
    step1 = card.steps[0]
    assert step1.phrasings == ()
    assert step1.gap is not None and "scheduled call" in step1.gap


def test_thin_target_info_leads_with_the_icebreaker(fw: Framework) -> None:
    assert is_thin(fw, "")
    assert is_thin(fw, "met at a mixer")
    card = compose(fw, "family_rooted", "cold_networking", target_notes="met at a mixer")
    assert card.thin_target_info and card.icebreaker_first
    assert card.steps[0].phrasings[0].icebreaker


def test_rich_target_info_puts_the_icebreaker_last(fw: Framework) -> None:
    assert not is_thin(fw, RICH)
    card = compose(fw, "family_rooted", "cold_networking", target_notes=RICH)
    assert not card.icebreaker_first
    assert not card.steps[0].phrasings[0].icebreaker
    assert card.steps[0].phrasings[-1].icebreaker


def test_thin_info_without_an_icebreaker_says_so(fw: Framework) -> None:
    card = compose(fw, "family_rooted", "potential_collaborator")
    assert card.thin_target_info and not card.icebreaker_first


def test_diagnostic_prompts_attach_to_step_4_only(fw: Framework) -> None:
    card = compose(fw, "empty_nester", "potential_collaborator", target_notes="Runs a food bank")
    assert all(not s.diagnostic_prompts for s in card.steps[:3])
    assert card.steps[3].diagnostic_prompts[0] == "From what you know about them: Runs a food bank"


def test_generosity_principle_only_on_giving_back(fw: Framework) -> None:
    for domain in fw.domains:
        card = compose(fw, "purpose_driven", domain.id)
        has = card.steps[3].principle_statement is not None
        assert has == (domain.id == "giving_back"), domain.id


def test_transcript_lines_come_before_prototype_lines(fw: Framework) -> None:
    for cluster, domain in itertools.product(fw.clusters, fw.domains):
        card = compose(fw, cluster.id, domain.id, target_notes=RICH)
        for step in card.steps:
            kinds = [p.source_kind for p in step.phrasings if not p.icebreaker]
            assert kinds == sorted(kinds, key=lambda k: k != "transcript"), step.id


def test_composition_is_deterministic(fw: Framework) -> None:
    a = compose(fw, "sandwich_caregiver", "casual_acquaintance", target_notes=RICH)
    b = compose(fw, "sandwich_caregiver", "casual_acquaintance", target_notes=RICH)
    assert a == b


def test_text_rendering_marks_examples_not_scripts(fw: Framework) -> None:
    out = render_text(compose(fw, "family_rooted", "giving_back"))
    assert "not scripts to read" in out
    assert "Principle:" in out
    assert "4. Earned ask" in out
