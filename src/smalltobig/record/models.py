"""The full-fidelity session record and its abstracted projection."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from smalltobig.models.session import Turn
from smalltobig.practice.htmsw_judge import StepVerdict

Source = Literal["rehearsal", "real"]
# DECISIONS #24: recording other people depends on where the conversation happens.
# Stored with full-profile debriefs only; a rehearsal has no third party.
Consent = Literal["obtained", "not_required_here", "own_side_only", "not_applicable"]


class SessionRecord(BaseModel):
    """Everything a session produced. Only the `full` profile ever writes this."""

    model_config = ConfigDict(frozen=True)

    source: Source
    domain_id: str
    created_at: datetime
    verdicts: tuple[StepVerdict, ...]
    cluster_id: str | None = None
    partner_id: str | None = None
    turns: tuple[Turn, ...] = ()
    account: str | None = None  # debrief prose about a real conversation
    consent: Consent = "not_applicable"
    model_messages: tuple[dict[str, str], ...] = ()
    model_reply: str | None = None


class Outcome(BaseModel):
    """One step result. Integers and enums only; this is all `abstracted` keeps."""

    model_config = ConfigDict(frozen=True)

    step_order: int = Field(ge=1)
    domain_id: str
    source: Source
    passed: bool
    at: int  # unix seconds
