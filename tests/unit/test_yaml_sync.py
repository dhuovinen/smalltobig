from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import yaml

from smalltobig.config import Settings
from smalltobig.models.rule import RubricItem, Rule, RuleStatus
from smalltobig.store import yaml_sync

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, repo_root=tmp_path / "repo")  # type: ignore[call-arg]


def _rule() -> Rule:
    return Rule(
        id="ask-follow-up-questions",
        name="Ask follow-up questions",
        imperative="Ask about what they just said.",
        rationale="Follow-ups signal responsiveness.",
        when_to_apply="Past the opening two turns.",
        antipattern="Changing the subject.",
        evidence_tier="A",
        status=RuleStatus.ACCEPTED,
        claims=["clm_1", "clm_2"],
        rubric=[RubricItem(id="asked_followup", check="Did you ask a follow-up?")],
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
        decided_at=datetime(2026, 9, 22, tzinfo=UTC),
    )


def test_write_rule_creates_a_readable_yaml_file(settings: Settings) -> None:
    yaml_sync.write_rule(settings, _rule())

    path = yaml_sync.rule_yaml_path(settings, "ask-follow-up-questions")
    assert path.exists()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["id"] == "ask-follow-up-questions"
    assert data["evidence_tier"] == "A"
    assert data["status"] == "accepted"
    assert data["claims"] == ["clm_1", "clm_2"]
    assert data["rubric"] == [{"id": "asked_followup", "check": "Did you ask a follow-up?"}]


def test_write_rule_creates_the_rules_directory(settings: Settings) -> None:
    assert not settings.rules_dir.exists()
    yaml_sync.write_rule(settings, _rule())
    assert settings.rules_dir.is_dir()


def test_remove_rule_deletes_the_file(settings: Settings) -> None:
    yaml_sync.write_rule(settings, _rule())
    path = yaml_sync.rule_yaml_path(settings, "ask-follow-up-questions")
    assert path.exists()

    yaml_sync.remove_rule(settings, "ask-follow-up-questions")
    assert not path.exists()


def test_remove_rule_is_a_no_op_when_no_file_exists(settings: Settings) -> None:
    # Rejecting a rule that was never accepted should not raise.
    yaml_sync.remove_rule(settings, "never-written")
