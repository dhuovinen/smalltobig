from __future__ import annotations

from typing import TYPE_CHECKING

from smalltobig.models.scenario import Persona, Scenario
from smalltobig.models.session import Turn
from smalltobig.practice.roleplay import generate_opening_line, generate_reply

if TYPE_CHECKING:
    from smalltobig.llm.client import ChatMessage


class _RecordingClient:
    """Captures the messages it was called with, for asserting on what
    the actor did and did not send."""

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.last_messages: list[ChatMessage] = []

    def health(self) -> bool:
        return True

    def chat(
        self, messages: list[ChatMessage], *, max_tokens: int = 256, temperature: float = 0.0
    ) -> str:
        self.last_messages = messages
        return self._reply


def _scenario() -> Scenario:
    return Scenario(
        id="elevator",
        name="Elevator",
        setting="A short elevator ride.",
        persona=Persona(
            name="Marcus",
            warmth="friendly",
            verbosity="terse",
            hidden_interest="He loves cycling.",
            private_instructions="You are Marcus, a coworker.",
        ),
    )


def test_generate_opening_line_strips_quotes() -> None:
    client = _RecordingClient('"Busy day?"')
    assert generate_opening_line(client, _scenario()) == "Busy day?"


def test_actor_system_prompt_carries_persona_but_never_rules() -> None:
    client = _RecordingClient("Busy day?")
    generate_opening_line(client, _scenario())

    system_message = client.last_messages[0]
    assert system_message["role"] == "system"
    assert "Marcus" in system_message["content"]
    assert "loves cycling" in system_message["content"]
    # Scenario's docstring promises private_instructions reach the actor; they
    # were silently dropped until the HTMSW live test caught a partner
    # inventing a different job.
    assert "You are Marcus, a coworker." in system_message["content"]
    # The actor's contract (practice/roleplay.py) never accepts a rules
    # argument at all, so there is no rubric text to leak — assert on the
    # concrete prompt as a belt-and-braces check.
    assert "rubric" not in system_message["content"].lower()
    assert "rule" not in system_message["content"].lower()


def test_generate_reply_maps_partner_turns_to_assistant_role() -> None:
    client = _RecordingClient("Not bad, you?")
    turns = [
        Turn(speaker="partner", text="Busy day?"),
        Turn(speaker="user", text="Yeah, hectic."),
    ]
    generate_reply(client, _scenario(), turns)

    roles = [m["role"] for m in client.last_messages]
    assert roles == ["system", "assistant", "user"]
    assert client.last_messages[1]["content"] == "Busy day?"
    assert client.last_messages[2]["content"] == "Yeah, hectic."
