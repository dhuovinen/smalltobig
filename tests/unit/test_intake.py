"""intake/: classification is pure and total; the profile stores flags only."""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

import pytest

from smalltobig.config import Settings
from smalltobig.framework.loader import load_framework
from smalltobig.intake import profile as self_profile
from smalltobig.intake.classify import IntakeError, classify, missing, normalize
from smalltobig.store import db

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

    from smalltobig.framework.loader import Framework


@pytest.fixture(scope="module")
def fw() -> Framework:
    return load_framework(Settings(_env_file=None).framework_dir)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("answers", "cluster"),
    [
        ({"has_kids": "no", "caregiving": "no", "primary_focus": "giving_back"}, "purpose_driven"),
        # giving_back outranks every family flag
        ({"has_kids": "yes", "kids_stage": "young", "caregiving": "yes",
          "primary_focus": "giving_back"}, "purpose_driven"),
        ({"has_kids": "yes", "kids_stage": "teen", "caregiving": "yes",
          "primary_focus": "family"}, "sandwich_caregiver"),
        ({"has_kids": "yes", "kids_stage": "university", "caregiving": "no",
          "primary_focus": "professional"}, "empty_nester"),
        ({"has_kids": "yes", "kids_stage": "independent", "caregiving": "no",
          "primary_focus": "family"}, "empty_nester"),
        ({"has_kids": "yes", "kids_stage": "young", "caregiving": "no",
          "primary_focus": "professional"}, "family_rooted"),
        ({"has_kids": "yes", "kids_stage": "teen", "caregiving": "no",
          "primary_focus": "family"}, "family_rooted"),
        # caregiving without children is not the sandwich generation here
        ({"has_kids": "no", "caregiving": "yes", "primary_focus": "family"},
         "professional_independent"),
        ({"has_kids": "no", "caregiving": "no", "primary_focus": "professional"},
         "professional_independent"),
        ({}, "professional_independent"),
    ],
)
def test_classify_branches(fw: Framework, answers: dict[str, str], cluster: str) -> None:
    assert classify(fw, answers).id == cluster


def test_classify_is_deterministic_over_every_answer_set(fw: Framework) -> None:
    stages = [None, "young", "teen", "university", "independent"]
    for kids, stage, care, focus in itertools.product(
        ["yes", "no"], stages, ["yes", "no"], ["professional", "family", "giving_back"]
    ):
        answers = {"has_kids": kids, "caregiving": care, "primary_focus": focus}
        if stage:
            answers["kids_stage"] = stage
        first = classify(fw, answers).id
        assert all(classify(fw, dict(answers)).id == first for _ in range(3))


def test_normalize_rejects_unknown_questions(fw: Framework) -> None:
    with pytest.raises(IntakeError, match="unknown intake question"):
        normalize(fw, {"child_name": "Ava"})


def test_normalize_rejects_free_text_answers(fw: Framework) -> None:
    with pytest.raises(IntakeError, match="must be one of"):
        normalize(fw, {"has_kids": "two, Ava and Leo"})


def test_normalize_drops_answers_that_no_longer_apply(fw: Framework) -> None:
    assert normalize(fw, {"has_kids": "no", "kids_stage": "teen"}) == {"has_kids": "no"}


def test_missing_honours_ask_if(fw: Framework) -> None:
    assert "kids_stage" not in missing(fw, {"has_kids": "no"})
    assert "kids_stage" in missing(fw, {"has_kids": "yes"})


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return db.connect(tmp_path / "stb.sqlite3")


def test_profile_round_trip(fw: Framework, conn: sqlite3.Connection) -> None:
    assert self_profile.load(conn) == {}
    stored = self_profile.save(
        conn, fw, {"has_kids": "yes", "kids_stage": "teen", "caregiving": "no",
                   "primary_focus": "family"}
    )
    assert self_profile.load(conn) == stored
    self_profile.save(conn, fw, {"has_kids": "no"})
    assert self_profile.load(conn) == {"has_kids": "no"}
    self_profile.clear(conn)
    assert self_profile.load(conn) == {}


def test_profile_never_stores_free_text(fw: Framework, conn: sqlite3.Connection) -> None:
    # FR-24: a sentinel offered as an answer must be refused and appear nowhere.
    sentinel = "SENTINEL-Ava-Huovinen-7731"
    with pytest.raises(IntakeError):
        self_profile.save(conn, fw, {"has_kids": "yes", "kids_stage": sentinel})
    with pytest.raises(IntakeError):
        self_profile.save(conn, fw, {sentinel: "yes"})
    rows = conn.execute("SELECT answers_json FROM self_profile").fetchall()
    assert all(sentinel not in row[0] for row in rows)
