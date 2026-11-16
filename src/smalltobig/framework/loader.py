"""Load and validate framework/*.yaml into typed models.

Fails loudly at startup on a malformed framework, never at request time
(IMPLEMENTATION.md Phase 2). Structural checks live here; content checks
(coverage, tier pinning, reachability) live in tests/test_framework.py.

No step, domain or phrasing text may be hard-coded elsewhere (FR-11): code
asks the `Framework` object by id.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

if TYPE_CHECKING:
    from pathlib import Path

Tier = Literal["A", "B", "C", "D"]


class FrameworkError(RuntimeError):
    """The framework YAML is missing, malformed or internally inconsistent."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class Step(_Model):
    id: str
    order: int
    name: str
    definition: str
    coaching: str
    antipattern: str
    evidence_tier: Tier
    basis: str
    rubric_item: str
    seed_rules: tuple[str, ...] = ()


class RubricItem(_Model):
    id: str
    step: str
    check: str


class IcebreakerLayer(_Model):
    definition: str
    applies_to: str
    evidence_tier: Tier
    basis: str
    thin_when_target_words_below: int = Field(ge=0)


class Principle(_Model):
    id: str
    statement: str
    orientation: str
    closing_patterns: tuple[str, ...]
    evidence_tier: Tier
    basis: str


class Domain(_Model):
    id: str
    name: str
    context: str
    pacing: str
    initial_stakes: str
    escalation_rule: str
    evidence_tier: Tier
    basis: str
    diagnostic_prompts: tuple[str, ...]
    principle: Principle | None = None


class Question(_Model):
    id: str
    prompt: str
    options: tuple[str, ...]
    option_labels: dict[str, str] = {}
    ask_if: dict[str, str] = {}

    @field_validator("options", mode="before")
    @classmethod
    def _options_are_strings(cls, value: Any) -> Any:
        # Unquoted yes/no in YAML become booleans and would never match an answer.
        if isinstance(value, list | tuple) and not all(isinstance(v, str) for v in value):
            raise ValueError(f"options must all be strings (quote yes/no): {value!r}")
        return value

    def label(self, option: str) -> str:
        return self.option_labels.get(option, option.replace("_", " ").capitalize())


class Cluster(_Model):
    id: str
    label: str
    description: str


class ClassificationRule(_Model):
    when: dict[str, str | tuple[str, ...]]
    cluster: str

    def matches(self, answers: dict[str, str]) -> bool:
        for key, expected in self.when.items():
            allowed = (expected,) if isinstance(expected, str) else expected
            if answers.get(key) not in allowed:
                return False
        return True


class PhrasingSource(_Model):
    kind: Literal["transcript", "prototype"]
    ref: str
    derived_from: str | None = None


class Phrasing(_Model):
    id: str
    step: str
    clusters: Literal["all"] | tuple[str, ...]
    domains: Literal["all"] | tuple[str, ...]
    text: str
    adapt: Literal[True]
    source: PhrasingSource
    layer: Literal["icebreaker"] | None = None
    calibration: str | None = None
    closing_pattern: bool = False

    def applies(self, cluster_id: str, domain_id: str) -> bool:
        return (self.clusters == "all" or cluster_id in self.clusters) and (
            self.domains == "all" or domain_id in self.domains
        )


class Gap(_Model):
    clusters: tuple[str, ...]
    domains: tuple[str, ...]
    step: str
    gap: str

    def applies(self, cluster_id: str, domain_id: str, step_id: str) -> bool:
        return (
            step_id == self.step and cluster_id in self.clusters and domain_id in self.domains
        )


class Framework(_Model):
    steps: tuple[Step, ...]
    rubric: tuple[RubricItem, ...]
    icebreaker_layer: IcebreakerLayer
    domains: tuple[Domain, ...]
    questions: tuple[Question, ...]
    clusters: tuple[Cluster, ...]
    classification: tuple[ClassificationRule, ...]
    phrasings: tuple[Phrasing, ...]
    gaps: tuple[Gap, ...]

    def step(self, step_id: str) -> Step:
        return _by_id(self.steps, step_id, "step")

    def domain(self, domain_id: str) -> Domain:
        return _by_id(self.domains, domain_id, "domain")

    def cluster(self, cluster_id: str) -> Cluster:
        return _by_id(self.clusters, cluster_id, "cluster")

    def question(self, question_id: str) -> Question:
        return _by_id(self.questions, question_id, "question")


_T = TypeVar("_T", Step, Domain, Cluster, Question)


def _by_id(items: tuple[_T, ...], key: str, kind: str) -> _T:
    for item in items:
        if item.id == key:
            return item
    raise KeyError(f"unknown {kind}: {key!r}")


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError as exc:
        raise FrameworkError(f"framework file missing: {path}") from exc
    except yaml.YAMLError as exc:
        raise FrameworkError(f"{path.name} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise FrameworkError(f"{path.name} must be a mapping")
    return data


def _check_references(fw: Framework) -> None:
    step_ids = {s.id for s in fw.steps}
    domain_ids = {d.id for d in fw.domains}
    cluster_ids = {c.id for c in fw.clusters}
    question_options = {q.id: set(q.options) for q in fw.questions}
    problems: list[str] = []

    for kind, ids in (
        ("step", [s.id for s in fw.steps]),
        ("domain", [d.id for d in fw.domains]),
        ("cluster", [c.id for c in fw.clusters]),
        ("phrasing", [p.id for p in fw.phrasings]),
    ):
        if len(ids) != len(set(ids)):
            problems.append(f"duplicate {kind} ids")
    rubric_ids = {r.id for r in fw.rubric}
    for s in fw.steps:
        if s.rubric_item not in rubric_ids:
            problems.append(f"{s.id}: unknown rubric item {s.rubric_item}")
    if fw.icebreaker_layer.applies_to not in step_ids:
        problems.append("icebreaker_layer.applies_to is not a step")
    for q in fw.questions:
        for key, value in q.ask_if.items():
            if value not in question_options.get(key, set()):
                problems.append(f"question {q.id}: ask_if {key}={value} is not a real answer")
    if not fw.classification or fw.classification[-1].when:
        problems.append("classification must end with a catch-all rule (when: {})")
    for rule in fw.classification:
        if rule.cluster not in cluster_ids:
            problems.append(f"classification targets unknown cluster {rule.cluster}")
        for key, expected in rule.when.items():
            allowed = {expected} if isinstance(expected, str) else set(expected)
            if key not in question_options or not allowed <= question_options[key]:
                problems.append(f"classification uses unknown answer {key}={expected}")
    for p in fw.phrasings:
        if p.step not in step_ids:
            problems.append(f"phrasing {p.id}: unknown step {p.step}")
        if p.clusters != "all" and not set(p.clusters) <= cluster_ids:
            problems.append(f"phrasing {p.id}: unknown cluster")
        if p.domains != "all" and not set(p.domains) <= domain_ids:
            problems.append(f"phrasing {p.id}: unknown domain")
    for g in fw.gaps:
        if g.step not in step_ids or not set(g.clusters) <= cluster_ids:
            problems.append(f"gap for {g.step}: unknown step or cluster")
        if not set(g.domains) <= domain_ids:
            problems.append(f"gap for {g.step}: unknown domain")
    if problems:
        raise FrameworkError("framework is inconsistent:\n  " + "\n  ".join(problems))


def load_framework(directory: Path) -> Framework:
    """Read and validate every framework file. Raises FrameworkError on any problem."""
    htmsw = _read(directory / "htmsw.yaml")
    domains = _read(directory / "domains.yaml")
    personas = _read(directory / "personas.yaml")
    phrasings = _read(directory / "phrasings.yaml")
    try:
        fw = Framework(
            steps=htmsw["steps"],
            rubric=htmsw["rubric"],
            icebreaker_layer=htmsw["icebreaker_layer"],
            domains=domains["domains"],
            questions=personas["questions"],
            clusters=personas["clusters"],
            classification=personas["classification"],
            phrasings=phrasings["phrasings"],
            gaps=phrasings.get("gaps", []),
        )
    except KeyError as exc:
        raise FrameworkError(f"framework file is missing section {exc}") from exc
    except ValidationError as exc:
        raise FrameworkError(f"framework failed validation:\n{exc}") from exc
    _check_references(fw)
    return fw


@lru_cache(maxsize=4)
def cached_framework(directory: Path) -> Framework:
    """Load once per directory per process. The YAML is reference data."""
    return load_framework(directory)
