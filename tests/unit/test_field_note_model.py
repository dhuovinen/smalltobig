from __future__ import annotations

from datetime import UTC, datetime

from smalltobig.models.field_note import generate_debrief_id, generate_field_note_id


def test_generate_debrief_id_is_deterministic_for_the_same_inputs() -> None:
    now = datetime(2026, 9, 22, tzinfo=UTC)
    assert generate_debrief_id("some text", now) == generate_debrief_id("some text", now)


def test_generate_debrief_id_differs_for_different_text() -> None:
    now = datetime(2026, 9, 22, tzinfo=UTC)
    assert generate_debrief_id("text a", now) != generate_debrief_id("text b", now)


def test_generate_field_note_id_is_deterministic() -> None:
    assert generate_field_note_id("dbf_1", "rule-a") == generate_field_note_id("dbf_1", "rule-a")


def test_generate_field_note_id_differs_per_rule() -> None:
    assert generate_field_note_id("dbf_1", "rule-a") != generate_field_note_id("dbf_1", "rule-b")
