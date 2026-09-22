"""Cluster accepted claims into candidate rules, then propose conflicts
among all rules. See docs/PLAN.md §5 Phase 3.

Deliberately not idempotent-by-replacement like extract_source: a rule or
conflict, once a human has decided it, must never be silently overwritten
by a re-run (docs/DECISIONS.md non-negotiable #2). Re-running skips any
cluster that already produced a rule and any pair that already has a
conflict record, in any status — new claims or new rules can still
produce genuinely new candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from smalltobig.embed.cluster import DEFAULT_SIMILARITY_THRESHOLD, cluster_by_similarity
from smalltobig.models.conflict import Conflict, ConflictStatus, generate_conflict_id
from smalltobig.models.rule import RubricItem, Rule, RuleStatus, generate_rule_id
from smalltobig.store import repo_claims, repo_conflicts, repo_rules
from smalltobig.synth.conflicts import find_conflict_candidates, judge_conflict
from smalltobig.synth.rules import draft_rule_from_cluster

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable

    from smalltobig.llm.client import LlmClient


@dataclass(frozen=True)
class SynthesisSummary:
    accepted_claims: int
    clusters: int
    rules_drafted: int
    rules_skipped_existing: int
    conflict_candidates: int
    conflicts_proposed: int


def _unique_rule_id(conn: sqlite3.Connection, name: str) -> str:
    base = generate_rule_id(name)
    candidate = base
    suffix = 2
    while repo_rules.get(conn, candidate) is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def synthesize_rules(
    conn: sqlite3.Connection,
    llm_client: LlmClient,
    embed: Callable[[list[str]], list[list[float]]],
    *,
    cluster_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> SynthesisSummary:
    claims = repo_claims.list_accepted(conn)
    if not claims:
        return SynthesisSummary(0, 0, 0, 0, 0, 0)

    paraphrase_embeddings = embed([claim.paraphrase for claim in claims])
    clusters = cluster_by_similarity(paraphrase_embeddings, threshold=cluster_threshold)

    now = datetime.now(UTC)
    drafted = 0
    skipped = 0
    for cluster in clusters:
        cluster_claims = [claims[i] for i in cluster.indices]
        claim_id_set = {claim.id for claim in cluster_claims}

        if repo_rules.find_by_claim_set(conn, claim_id_set) is not None:
            skipped += 1
            continue

        proposed = draft_rule_from_cluster(llm_client, cluster_claims)
        if proposed is None:
            continue

        rule = Rule(
            id=_unique_rule_id(conn, proposed.name),
            name=proposed.name,
            imperative=proposed.imperative,
            rationale=proposed.rationale,
            when_to_apply=proposed.when_to_apply,
            antipattern=proposed.antipattern,
            evidence_tier=proposed.evidence_tier,
            status=RuleStatus.CANDIDATE,
            claims=sorted(claim_id_set),
            rubric=[RubricItem(id=item.id, check=item.check) for item in proposed.rubric],
            created_at=now,
        )
        repo_rules.create(conn, rule)
        drafted += 1

    # Conflict detection runs over ALL rules, old and new, so a fresh
    # candidate also gets checked against previously-accepted rules.
    all_rules = repo_rules.list_all(conn)
    candidates: list[tuple[Rule, Rule]] = []
    proposed_count = 0
    if len(all_rules) >= 2:
        rule_embeddings_list = embed([rule.imperative for rule in all_rules])
        rule_embeddings = dict(
            zip((rule.id for rule in all_rules), rule_embeddings_list, strict=True)
        )
        candidates = find_conflict_candidates(all_rules, rule_embeddings)

        for rule_a, rule_b in candidates:
            if repo_conflicts.get_by_pair(conn, rule_a.id, rule_b.id) is not None:
                continue
            judged = judge_conflict(llm_client, rule_a, rule_b)
            if judged is None or not judged.conflict:
                continue
            conflict = Conflict(
                id=generate_conflict_id(rule_a.id, rule_b.id),
                between=sorted([rule_a.id, rule_b.id]),
                note=judged.note,
                status=ConflictStatus.PROPOSED,
                proposed_resolution=judged.proposed_resolution or None,
                created_at=now,
            )
            repo_conflicts.create(conn, conflict)
            proposed_count += 1

    return SynthesisSummary(
        accepted_claims=len(claims),
        clusters=len(clusters),
        rules_drafted=drafted,
        rules_skipped_existing=skipped,
        conflict_candidates=len(candidates),
        conflicts_proposed=proposed_count,
    )
