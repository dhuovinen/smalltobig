from __future__ import annotations

from datetime import UTC, datetime

from smalltobig.models.mastery import Mastery, SignalType
from smalltobig.progress.leitner import apply_signal

NOW = datetime(2026, 9, 22, tzinfo=UTC)
LATER = datetime(2026, 9, 23, tzinfo=UTC)


def _mastery(**overrides: object) -> Mastery:
    defaults: dict[str, object] = {
        "rule_id": "some-rule",
        "box": 1,
        "score": 0.0,
        "has_non_drill_evidence": False,
        "updated_at": NOW,
    }
    defaults.update(overrides)
    return Mastery(**defaults)  # type: ignore[arg-type]


def test_drill_success_promotes_one_box() -> None:
    result = apply_signal(_mastery(box=1), SignalType.DRILL, success=True, now=LATER)
    assert result.box == 2
    assert result.updated_at == LATER


def test_any_signal_failure_resets_to_box_one() -> None:
    result = apply_signal(_mastery(box=4), SignalType.DRILL, success=False, now=LATER)
    assert result.box == 1


def test_drills_alone_cap_at_box_four() -> None:
    mastery = _mastery(box=4, has_non_drill_evidence=False)
    result = apply_signal(mastery, SignalType.DRILL, success=True, now=LATER)
    assert result.box == 4
    assert result.has_non_drill_evidence is False


def test_a_roleplay_signal_unlocks_the_top_box() -> None:
    mastery = _mastery(box=4, has_non_drill_evidence=False)
    result = apply_signal(mastery, SignalType.ROLEPLAY, success=True, now=LATER)
    assert result.box == 5
    assert result.has_non_drill_evidence is True


def test_a_failed_roleplay_signal_still_unlocks_the_ceiling() -> None:
    # Evidence has entered the record even if this particular attempt failed.
    mastery = _mastery(box=3, has_non_drill_evidence=False)
    result = apply_signal(mastery, SignalType.ROLEPLAY, success=False, now=LATER)
    assert result.box == 1
    assert result.has_non_drill_evidence is True


def test_once_unlocked_a_drill_success_can_reach_box_five() -> None:
    mastery = _mastery(box=4, has_non_drill_evidence=True)
    result = apply_signal(mastery, SignalType.DRILL, success=True, now=LATER)
    assert result.box == 5


def test_box_five_drill_success_stays_at_five() -> None:
    mastery = _mastery(box=5, has_non_drill_evidence=True)
    result = apply_signal(mastery, SignalType.DRILL, success=True, now=LATER)
    assert result.box == 5


def test_score_increases_on_success_by_the_signal_weight() -> None:
    result = apply_signal(_mastery(score=0.0), SignalType.DRILL, success=True, now=LATER)
    assert result.score == 0.5

    result = apply_signal(_mastery(score=0.0), SignalType.ROLEPLAY, success=True, now=LATER)
    assert result.score == 1.0

    result = apply_signal(_mastery(score=0.0), SignalType.FIELD_NOTE, success=True, now=LATER)
    assert result.score == 3.0


def test_score_decreases_on_failure_and_never_goes_negative() -> None:
    result = apply_signal(_mastery(score=0.3), SignalType.DRILL, success=False, now=LATER)
    assert result.score == 0.0

    result = apply_signal(_mastery(score=1.0), SignalType.FIELD_NOTE, success=False, now=LATER)
    assert result.score == 0.0
