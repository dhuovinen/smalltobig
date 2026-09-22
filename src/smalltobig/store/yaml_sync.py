"""Sync accepted rules to `rules/<id>.yaml` — plain, git-tracked, greppable
and diffable without the app running (docs/PLAN.md §6).

One-way, DB -> disk, on every accept/reject/supersede transition. This is
deliberately narrower than the "two-way synced" persistence described in
docs/PLAN.md §4: hand-editing a YAML file and having it flow back into the
database would need a file watcher and a merge policy neither doc nor
seed data specifies, so it isn't built. The database stays the source of
truth for workflow state; `rules/` is the readable, portable export of it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from pathlib import Path

    from smalltobig.config import Settings
    from smalltobig.models.rule import Rule

def rule_yaml_path(settings: Settings, rule_id: str) -> Path:
    return settings.rules_dir / f"{rule_id}.yaml"


def write_rule(settings: Settings, rule: Rule) -> None:
    """Only ever called for status == accepted — see docs/PLAN.md §6:
    "rules/ being plain git-tracked YAML... the rule set is the thing you
    are building"."""
    data = {
        "id": rule.id,
        "name": rule.name,
        "imperative": rule.imperative,
        "rationale": rule.rationale,
        "when_to_apply": rule.when_to_apply,
        "antipattern": rule.antipattern,
        "evidence_tier": rule.evidence_tier,
        "status": rule.status.value,
        "claims": rule.claims,
        "prerequisites": rule.prerequisites,
        "rubric": [item.model_dump() for item in rule.rubric],
    }
    path = rule_yaml_path(settings, rule.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def remove_rule(settings: Settings, rule_id: str) -> None:
    """Called when a previously-accepted rule is superseded or rejected —
    only accepted rules belong in the on-disk output."""
    path = rule_yaml_path(settings, rule_id)
    path.unlink(missing_ok=True)
