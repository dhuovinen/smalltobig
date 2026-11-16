"""Compose a prep card from curated phrasings.

Pure composition from framework/*.yaml (FR-31). This module makes zero model calls
and zero network calls (FR-34, NFR-13), and must not import anything that could:
tests/unit/test_prep_offline.py enforces both. Do not "improve" phrasings with a
model here; a model-adapted variant is a later phase and stays anchored to these
curated examples.

The card is ephemeral (REQUIREMENTS.md §5): it is regenerable from cluster and
domain, and nothing here writes to disk.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from smalltobig.framework.loader import Framework, Phrasing


class _View(BaseModel):
    model_config = ConfigDict(frozen=True)


class PhrasingView(_View):
    id: str
    text: str
    source_kind: str
    source_ref: str
    icebreaker: bool
    domain_agnostic: bool
    closing_pattern: bool


class StepCard(_View):
    id: str
    order: int
    name: str
    definition: str
    coaching: str
    antipattern: str
    evidence_tier: str
    phrasings: tuple[PhrasingView, ...]
    gap: str | None
    diagnostic_prompts: tuple[str, ...] = ()
    principle_statement: str | None = None


class PrepCard(_View):
    cluster_id: str
    cluster_label: str
    domain_id: str
    domain_name: str
    domain_context: str
    pacing: str
    initial_stakes: str
    escalation_rule: str
    domain_tier: str
    thin_target_info: bool
    icebreaker_first: bool
    target_note: str | None
    steps: tuple[StepCard, ...]

    @property
    def complete(self) -> bool:
        """Every step has at least one phrasing or an explicit gap."""
        return len(self.steps) == 4 and all(s.phrasings or s.gap for s in self.steps)


def is_thin(fw: Framework, target_notes: str) -> bool:
    """FR-33: is what the user knows about the other person too little to tailor from?"""
    return len(target_notes.split()) < fw.icebreaker_layer.thin_when_target_words_below


def _view(p: Phrasing) -> PhrasingView:
    return PhrasingView(
        id=p.id,
        text=p.text,
        source_kind=p.source.kind,
        source_ref=p.source.ref,
        icebreaker=p.layer == "icebreaker",
        domain_agnostic=p.calibration == "domain_agnostic",
        closing_pattern=p.closing_pattern,
    )


def _order(phrasings: list[Phrasing], *, icebreaker_first: bool) -> list[Phrasing]:
    # Stable sort: icebreakers first only when target info is thin, then
    # transcript-tested lines before prototype ones, otherwise YAML order.
    def key(p: Phrasing) -> tuple[int, int]:
        is_ice = p.layer == "icebreaker"
        ice_rank = (0 if is_ice else 1) if icebreaker_first else (1 if is_ice else 0)
        return (ice_rank, 0 if p.source.kind == "transcript" else 1)

    return sorted(phrasings, key=key)


def compose(fw: Framework, cluster_id: str, domain_id: str, *, target_notes: str = "") -> PrepCard:
    """Build the four-step prep card for one (cluster, domain) pair.

    `target_notes` is what the user knows about the other person. It only decides
    whether the icebreaker layer leads (FR-33) and is echoed back as a reminder on
    step 4. It is never stored.
    """
    cluster = fw.cluster(cluster_id)
    domain = fw.domain(domain_id)
    notes = target_notes.strip()
    thin = is_thin(fw, notes)
    icebreaker_step = fw.icebreaker_layer.applies_to

    steps: list[StepCard] = []
    for step in sorted(fw.steps, key=lambda s: s.order):
        applicable = [
            p for p in fw.phrasings if p.step == step.id and p.applies(cluster.id, domain.id)
        ]
        ordered = _order(applicable, icebreaker_first=thin and step.id == icebreaker_step)
        gap = next(
            (g.gap for g in fw.gaps if g.applies(cluster.id, domain.id, step.id)), None
        )
        is_last = step.order == max(s.order for s in fw.steps)
        prompts: tuple[str, ...] = ()
        principle: str | None = None
        if is_last:
            # FR-35: diagnostic prompts attach to the final step, the earned ask.
            prompts = domain.diagnostic_prompts
            if notes:
                prompts = (f"From what you know about them: {notes}", *prompts)
            if domain.principle is not None:
                principle = domain.principle.statement
        steps.append(
            StepCard(
                id=step.id,
                order=step.order,
                name=step.name,
                definition=step.definition,
                coaching=step.coaching,
                antipattern=step.antipattern,
                evidence_tier=step.evidence_tier,
                phrasings=tuple(_view(p) for p in ordered),
                gap=gap,
                diagnostic_prompts=prompts,
                principle_statement=principle,
            )
        )

    has_icebreaker = any(
        p.icebreaker for s in steps if s.id == icebreaker_step for p in s.phrasings
    )
    return PrepCard(
        cluster_id=cluster.id,
        cluster_label=cluster.label,
        domain_id=domain.id,
        domain_name=domain.name,
        domain_context=domain.context,
        pacing=domain.pacing,
        initial_stakes=domain.initial_stakes,
        escalation_rule=domain.escalation_rule,
        domain_tier=domain.evidence_tier,
        thin_target_info=thin,
        icebreaker_first=thin and has_icebreaker,
        target_note=notes or None,
        steps=tuple(steps),
    )


def render_text(card: PrepCard) -> str:
    """Plain-text rendering for `stb prep`."""
    lines = [
        f"HTMSW prep card · {card.domain_name} · you: {card.cluster_label}",
        f"Pacing: {card.pacing}",
        f"Stakes to start: {card.initial_stakes.replace('_', ' ')}. "
        f"Move on when: {card.escalation_rule}",
        f"(Domain pacing is evidence tier {card.domain_tier}: a hypothesis being tested.)",
    ]
    if card.thin_target_info:
        lines.append(
            "Little known about them: lead with a low-stakes icebreaker."
            if card.icebreaker_first
            else "Little known about them, and no icebreaker exists for this domain yet."
        )
    lines.append("Examples to adapt into your own words, not scripts to read.")
    for step in card.steps:
        lines += [
            "",
            f"{step.order}. {step.name}  [tier {step.evidence_tier}]",
            f"   {step.coaching}",
        ]
        for p in step.phrasings:
            tags = [p.source_kind]
            if p.icebreaker:
                tags.append("icebreaker")
            if p.domain_agnostic:
                tags.append("not sized to this domain")
            lines.append(f"   - \"{p.text}\"  ({', '.join(tags)})")
        if step.gap:
            lines.append(f"   ! No curated example: {step.gap}")
        if step.principle_statement:
            lines.append(f"   Principle: {step.principle_statement}")
        for prompt in step.diagnostic_prompts:
            lines.append(f"   ? {prompt}")
    return "\n".join(lines)
