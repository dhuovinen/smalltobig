from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from smalltobig.config import Settings
from smalltobig.extract.pipeline import UnknownSourceError, extract_source
from smalltobig.ingest.paste import ingest_pasted_text
from smalltobig.models.source import SourceKind
from smalltobig.store import db, repo_claims

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path

    from smalltobig.llm.client import ChatMessage

SOURCE_TEXT = (
    "Ask follow-up questions when they finish answering. Do not multitask "
    "during a conversation."
)


class _ScriptedClient:
    """Returns each reply in order, one per chat() call — one call per chunk."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)

    def health(self) -> bool:
        return True

    def chat(
        self, messages: list[ChatMessage], *, max_tokens: int = 256, temperature: float = 0.0
    ) -> str:
        return self._replies.pop(0)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]


@pytest.fixture
def conn(settings: Settings) -> Iterator[sqlite3.Connection]:
    connection = db.connect(settings.db_path)
    yield connection
    connection.close()


@pytest.fixture
def source_id(conn: sqlite3.Connection, settings: Settings) -> str:
    source = ingest_pasted_text(
        conn, settings, text=SOURCE_TEXT, title="Test Source", kind=SourceKind.NOTES
    )
    return source.id


def test_extract_source_accepts_real_quotes_and_rejects_invented_ones(
    conn: sqlite3.Connection, settings: Settings, source_id: str
) -> None:
    reply = json.dumps(
        [
            {
                "verbatim": "Ask follow-up questions when they finish answering.",
                "paraphrase": "Follow up on their answer.",
                "claim_type": "prescriptive",
            },
            {
                "verbatim": "Always make eye contact and smile warmly.",  # not in source
                "paraphrase": "Eye contact matters.",
                "claim_type": "prescriptive",
            },
        ]
    )
    client = _ScriptedClient([reply])

    summary = extract_source(conn, settings, client, source_id)

    assert summary.proposed == 2
    assert summary.accepted == 1
    assert summary.rejected == 1
    assert summary.rejection_rate == pytest.approx(0.5)

    claims = repo_claims.list_by_source(conn, source_id)
    assert len(claims) == 2
    accepted = [c for c in claims if c.status.value == "accepted"][0]
    rejected = [c for c in claims if c.status.value == "rejected"][0]
    assert accepted.start is not None and accepted.end is not None
    assert rejected.rejection_reason == "span not found in source"


def test_extract_source_raises_for_unknown_source(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    with pytest.raises(UnknownSourceError):
        extract_source(conn, settings, _ScriptedClient([]), "src_does_not_exist")


def test_re_extraction_replaces_rather_than_accumulates_claims(
    conn: sqlite3.Connection, settings: Settings, source_id: str
) -> None:
    first_reply = json.dumps(
        [
            {
                "verbatim": "Ask follow-up questions when they finish answering.",
                "paraphrase": "Follow up.",
                "claim_type": "prescriptive",
            }
        ]
    )
    second_reply = json.dumps(
        [
            {
                "verbatim": "Do not multitask during a conversation.",
                "paraphrase": "Be present.",
                "claim_type": "prescriptive",
            }
        ]
    )

    extract_source(conn, settings, _ScriptedClient([first_reply]), source_id)
    assert len(repo_claims.list_by_source(conn, source_id)) == 1

    extract_source(conn, settings, _ScriptedClient([second_reply]), source_id)
    claims = repo_claims.list_by_source(conn, source_id)
    assert len(claims) == 1
    assert claims[0].verbatim == "Do not multitask during a conversation."


def test_a_model_failure_partway_keeps_the_previous_claims(
    conn: sqlite3.Connection, settings: Settings, source_id: str
) -> None:
    reply = json.dumps(
        [
            {
                "verbatim": "Ask follow-up questions when they finish answering.",
                "paraphrase": "Follow up.",
                "claim_type": "prescriptive",
            }
        ]
    )
    extract_source(conn, settings, _ScriptedClient([reply]), source_id)
    before = repo_claims.list_by_source(conn, source_id)
    assert len(before) == 1

    with pytest.raises(IndexError):  # _ScriptedClient runs out of replies, like a dead server
        extract_source(conn, settings, _ScriptedClient([]), source_id)

    assert repo_claims.list_by_source(conn, source_id) == before
