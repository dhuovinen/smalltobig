from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from smalltobig.models.claim import Claim, ClaimStatus, ClaimType
from smalltobig.models.rule import RuleStatus
from smalltobig.models.source import Source, SourceKind
from smalltobig.store import db, repo_claims, repo_conflicts, repo_rules, repo_sources
from smalltobig.synth.pipeline import synthesize_rules

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path

    from smalltobig.llm.client import ChatMessage

RULE_REPLY = (
    '{"name": "Ask follow-up questions", '
    '"imperative": "Ask about what they just said.", '
    '"rationale": "Follow-ups signal responsiveness.", '
    '"when_to_apply": "Past the opening two turns.", '
    '"antipattern": "Changing the subject.", '
    '"evidence_tier": "A", '
    '"rubric": [{"id": "asked_followup", "check": "Did you ask a follow-up?"}]}'
)

RULE_REPLY_B = (
    '{"name": "Never bring up X", '
    '"imperative": "Never bring up X directly.", '
    '"rationale": "Bringing up X backfires.", '
    '"when_to_apply": "Whenever X is tempting.", '
    '"antipattern": "Mentioning X anyway.", '
    '"evidence_tier": "B", '
    '"rubric": [{"id": "avoided_x", "check": "Did you avoid mentioning X?"}]}'
)

NO_CONFLICT_REPLY = '{"conflict": false, "note": "", "proposed_resolution": ""}'
CONFLICT_REPLY = '{"conflict": true, "note": "Contradictory.", "proposed_resolution": "Pick one."}'


def _conflict_test_embed(texts: list[str]) -> list[list[float]]:
    """Content-aware fake embeddings: the two claim paraphrases land far
    apart (so they form separate clusters), while the two rules' resulting
    imperatives land at cosine similarity 0.8 — inside the default
    conflict-candidate band (0.55 <= sim < 0.92)."""
    vectors_by_text = {
        "do x": [1.0, 0.0],
        "never x": [-1.0, 0.0],
        "Ask about what they just said.": [1.0, 0.0],
        "Never bring up X directly.": [0.8, 0.6],
    }
    return [vectors_by_text.get(text, [0.0, 1.0]) for text in texts]


class _ScriptedClient:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)

    def health(self) -> bool:
        return True

    def chat(
        self, messages: list[ChatMessage], *, max_tokens: int = 256, temperature: float = 0.0
    ) -> str:
        return self._replies.pop(0)


def _identity_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic fake embeddings: same text -> same vector, and texts
    sharing a first word cluster together, so tests don't need mlx."""
    vectors = []
    for text in texts:
        bucket = hash(text.split()[0]) % 1000
        vectors.append([float(bucket), 1.0])
    return vectors


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def _seed_source_and_claims(conn: sqlite3.Connection, claims: list[Claim]) -> None:
    repo_sources.create(
        conn,
        Source(
            id="src_1",
            title="Source",
            kind=SourceKind.NOTES,
            retrieved_at=datetime(2026, 9, 22, tzinfo=UTC),
            sha256="a" * 64,
        ),
        raw_extension=".txt",
    )
    for claim in claims:
        repo_claims.create(conn, claim)


def _claim(claim_id: str, verbatim: str, paraphrase: str) -> Claim:
    return Claim(
        id=claim_id,
        source_id="src_1",
        chunk_index=0,
        verbatim=verbatim,
        paraphrase=paraphrase,
        claim_type=ClaimType.EMPIRICAL_FINDING,
        status=ClaimStatus.ACCEPTED,
        start=0,
        end=len(verbatim),
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
    )


def test_no_accepted_claims_yields_an_empty_summary(conn: sqlite3.Connection) -> None:
    summary = synthesize_rules(conn, _ScriptedClient([]), _identity_embed)
    assert summary.accepted_claims == 0
    assert summary.clusters == 0
    assert summary.rules_drafted == 0


def test_drafts_one_rule_from_a_single_cluster(conn: sqlite3.Connection) -> None:
    claims = [_claim("clm_1", "Ask follow-up questions.", "followup one")]
    _seed_source_and_claims(conn, claims)

    summary = synthesize_rules(conn, _ScriptedClient([RULE_REPLY]), _identity_embed)

    assert summary.accepted_claims == 1
    assert summary.clusters == 1
    assert summary.rules_drafted == 1
    rules = repo_rules.list_all(conn)
    assert len(rules) == 1
    assert rules[0].claims == ["clm_1"]
    assert rules[0].status.value == "candidate"


def test_rerunning_synthesis_does_not_duplicate_a_rule_for_the_same_cluster(
    conn: sqlite3.Connection,
) -> None:
    claims = [_claim("clm_1", "Ask follow-up questions.", "followup one")]
    _seed_source_and_claims(conn, claims)

    synthesize_rules(conn, _ScriptedClient([RULE_REPLY]), _identity_embed)
    summary_two = synthesize_rules(conn, _ScriptedClient([]), _identity_embed)

    assert summary_two.rules_drafted == 0
    assert summary_two.rules_skipped_existing == 1
    assert len(repo_rules.list_all(conn)) == 1


def test_rerunning_synthesis_never_touches_a_decided_rule(conn: sqlite3.Connection) -> None:
    claims = [_claim("clm_1", "Ask follow-up questions.", "followup one")]
    _seed_source_and_claims(conn, claims)
    synthesize_rules(conn, _ScriptedClient([RULE_REPLY]), _identity_embed)

    rule_id = repo_rules.list_all(conn)[0].id
    repo_rules.set_status(conn, rule_id, RuleStatus.ACCEPTED, decided_at=datetime.now(UTC))

    synthesize_rules(conn, _ScriptedClient([]), _identity_embed)

    rule = repo_rules.get(conn, rule_id)
    assert rule is not None
    assert rule.status.value == "accepted"


def test_a_cluster_the_model_fails_to_draft_is_skipped_without_crashing(
    conn: sqlite3.Connection,
) -> None:
    claims = [_claim("clm_1", "Ask follow-up questions.", "followup one")]
    _seed_source_and_claims(conn, claims)

    summary = synthesize_rules(conn, _ScriptedClient(["not valid json"]), _identity_embed)

    assert summary.rules_drafted == 0
    assert repo_rules.list_all(conn) == []


def test_conflicts_are_proposed_between_topically_related_rules(
    conn: sqlite3.Connection,
) -> None:
    claims = [
        _claim("clm_1", "Do X.", "do x"),
        _claim("clm_2", "Never do X.", "never x"),
    ]
    _seed_source_and_claims(conn, claims)

    summary = synthesize_rules(
        conn,
        _ScriptedClient([RULE_REPLY, RULE_REPLY_B, CONFLICT_REPLY]),
        _conflict_test_embed,
    )

    assert summary.rules_drafted == 2
    assert summary.conflicts_proposed == 1
    conflicts = repo_conflicts.list_all(conn)
    assert len(conflicts) == 1
    assert conflicts[0].note == "Contradictory."


def test_rerunning_does_not_duplicate_an_already_recorded_conflict(
    conn: sqlite3.Connection,
) -> None:
    claims = [
        _claim("clm_1", "Do X.", "do x"),
        _claim("clm_2", "Never do X.", "never x"),
    ]
    _seed_source_and_claims(conn, claims)

    synthesize_rules(
        conn,
        _ScriptedClient([RULE_REPLY, RULE_REPLY_B, CONFLICT_REPLY]),
        _conflict_test_embed,
    )
    summary_two = synthesize_rules(conn, _ScriptedClient([]), _conflict_test_embed)

    assert summary_two.conflicts_proposed == 0
    assert len(repo_conflicts.list_all(conn)) == 1
