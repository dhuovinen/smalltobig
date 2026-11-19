"""The HTMSW judge reference set: labelled conversations, run against the live model.

`evals/htmsw_reference.yaml` holds rehearsals (scored by `htmsw_judge`) and debrief
accounts (scored by `htmsw_debrief`), each with the verdict a careful human gives for
every step. `run` sends each case through the same code the app uses and compares.

Nothing here writes anywhere: reference runs are never recorded as sessions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from smalltobig.models.session import Turn
from smalltobig.practice import htmsw_debrief, htmsw_judge

if TYPE_CHECKING:
    from smalltobig.framework.loader import Framework
    from smalltobig.llm.client import LlmClient

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "evals" / "htmsw_reference.yaml"
Kind = Literal["rehearsal", "debrief"]


class _Case(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    note: str
    expected: tuple[bool, ...] = Field(min_length=4, max_length=4)


class RehearsalCase(_Case):
    turns: tuple[Turn, ...]

    @field_validator("turns", mode="before")
    @classmethod
    def _speaker_maps(cls, raw: list[dict[str, str]]) -> list[Turn]:
        turns = []
        for item in raw:
            if len(item) != 1:
                raise ValueError(f"each turn is one 'partner:' or 'user:' line, got {item}")
            ((speaker, text),) = item.items()
            turns.append(Turn(speaker=speaker, text=str(text).strip()))
        return turns


class DebriefCase(_Case):
    account: str


class ReferenceSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    rehearsals: tuple[RehearsalCase, ...]
    debriefs: tuple[DebriefCase, ...]

    @field_validator("debriefs")
    @classmethod
    def _unique_ids(
        cls, debriefs: tuple[DebriefCase, ...], info: ValidationInfo
    ) -> tuple[DebriefCase, ...]:
        ids = [c.id for c in info.data.get("rehearsals", ())] + [c.id for c in debriefs]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate case ids: {sorted(dupes)}")
        return debriefs


def load(path: Path = DEFAULT_PATH) -> ReferenceSet:
    return ReferenceSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class CaseResult:
    kind: Kind
    case_id: str
    expected: tuple[bool, ...]
    got: tuple[bool, ...]
    reasons: tuple[str | None, ...]

    @property
    def mismatches(self) -> list[int]:
        """Step orders (1-based) where the model disagreed with the label."""
        return [i for i, (e, g) in enumerate(zip(self.expected, self.got, strict=True), 1)
                if e != g]


@dataclass
class Report:
    results: list[CaseResult] = field(default_factory=list)

    def agreement(self, kind: Kind, step: int) -> tuple[int, int]:
        """(agreed, total) for one step order across cases of one kind."""
        cases = [r for r in self.results if r.kind == kind]
        return sum(r.expected[step - 1] == r.got[step - 1] for r in cases), len(cases)

    def errors(self, kind: Kind, step: int) -> tuple[int, int]:
        """(wrong yes, wrong not yet) for one step order across cases of one kind."""
        cases = [r for r in self.results if r.kind == kind]
        wrong_yes = sum(r.got[step - 1] and not r.expected[step - 1] for r in cases)
        wrong_no = sum(r.expected[step - 1] and not r.got[step - 1] for r in cases)
        return wrong_yes, wrong_no


def run(client: LlmClient, fw: Framework, refset: ReferenceSet) -> Report:
    report = Report()
    for rc in refset.rehearsals:
        verdicts = htmsw_judge.judge(client, fw, list(rc.turns))
        report.results.append(CaseResult(
            kind="rehearsal", case_id=rc.id, expected=rc.expected,
            got=tuple(v.passed for v in verdicts), reasons=tuple(v.reason for v in verdicts),
        ))
    for dc in refset.debriefs:
        verdicts, _, _ = htmsw_debrief.extract(client, fw, dc.account)
        report.results.append(CaseResult(
            kind="debrief", case_id=dc.id, expected=dc.expected,
            got=tuple(v.passed for v in verdicts), reasons=tuple(v.reason for v in verdicts),
        ))
    return report
