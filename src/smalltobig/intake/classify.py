"""Classify intake answers into a persona cluster.

A pure function of the answered flags (FR-23): no I/O, no model, no randomness.
The questions and rules are data in framework/personas.yaml (FR-28); this module
only evaluates them, first matching rule wins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from smalltobig.framework.loader import Cluster, Framework, Question


class IntakeError(ValueError):
    """Answers that name an unknown question or an option the question does not offer."""


def applicable_questions(fw: Framework, answers: Mapping[str, str]) -> list[Question]:
    """The questions that apply given the answers so far, honouring `ask_if`."""
    return [
        q for q in fw.questions if all(answers.get(k) == v for k, v in q.ask_if.items())
    ]


def normalize(fw: Framework, answers: Mapping[str, str | None]) -> dict[str, str]:
    """Validate answers and drop any that no longer apply.

    Every stored value is one of a question's fixed options, which is what keeps
    free text out of the self-profile (FR-24). Blank values are treated as
    unanswered. An answer to a question whose `ask_if` is unmet (for example a
    kids stage after answering "no" to children) is dropped, not kept stale.
    """
    known = {q.id: q for q in fw.questions}
    cleaned: dict[str, str] = {}
    for key, value in answers.items():
        if value is None or value == "":
            continue
        if key not in known:
            raise IntakeError(f"unknown intake question: {key!r}")
        if value not in known[key].options:
            raise IntakeError(
                f"{key!r} must be one of {list(known[key].options)}, not {value!r}"
            )
        cleaned[key] = value
    applicable = {q.id for q in applicable_questions(fw, cleaned)}
    return {k: v for k, v in cleaned.items() if k in applicable}


def missing(fw: Framework, answers: Mapping[str, str]) -> list[str]:
    """Ids of applicable questions that still have no answer."""
    return [q.id for q in applicable_questions(fw, answers) if q.id not in answers]


def classify(fw: Framework, answers: Mapping[str, str]) -> Cluster:
    """Return the persona cluster for these answers.

    Unanswered questions simply fail to match the rules that need them, so a
    partial intake still classifies (to the catch-all at worst). Use `missing()`
    to decide whether to ask for more.
    """
    normalized = normalize(fw, answers)
    for rule in fw.classification:
        if rule.matches(normalized):
            return fw.cluster(rule.cluster)
    # The loader guarantees a final catch-all rule, so this is unreachable.
    raise AssertionError("classification has no catch-all rule")
