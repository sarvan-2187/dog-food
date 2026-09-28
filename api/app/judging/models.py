"""Rubrics and judge assignments (PLAN.md Phase 2, section 8)."""
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from ..timeutil import utcnow


def _ts_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False)


def _nullable_ts_column() -> Column:
    return Column(DateTime(timezone=True), nullable=True)


def _invite_token() -> str:
    return secrets.token_urlsafe(16)


def _default_invite_expiry() -> datetime:
    return utcnow() + timedelta(days=14)


class JudgeInvite(SQLModel, table=True):
    """An organizer-issued invitation that brings a judge onto the platform.

    `judge` is the one role with no self-service path, by design -- self-serve judge
    signup would let anyone grant themselves sight of every score. So the only route in
    is an invitation issued by an organizer or admin, single-use and expiring, with both
    conditions checked server-side rather than by hiding a link (PLAN.md section 8.0).

    Deliberately not scoped to an event: judge accounts are global, matching how the
    assignment query already selects judges (see Open Questions).
    """

    __tablename__ = "judge_invites"

    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(default_factory=_invite_token, unique=True, index=True)
    # Who it was meant for. A note for the organizer's own tracking -- redemption is not
    # gated on it, since requiring a match would break the common case of someone
    # signing up with a different address than the one they were emailed at.
    invited_email: str = ""
    note: str = ""
    created_by_id: int = Field(foreign_key="users.id", index=True)
    expires_at: datetime = Field(default_factory=_default_invite_expiry, sa_column=_ts_column())
    redeemed_at: Optional[datetime] = Field(default=None, sa_column=_nullable_ts_column())
    redeemed_by_id: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())


class Rubric(SQLModel, table=True):
    """One rubric per event -- see Open Questions. `criteria` is a list of
    {key, label, weight, max_score}; the weights must sum to 1.0, which
    `RubricWrite` enforces on every write."""

    __tablename__ = "rubrics"

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="events.id", unique=True, index=True)
    name: str
    criteria: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())


class JudgeAssignment(SQLModel, table=True):
    """A judge's mandate to score one submission. The unique constraint is what
    makes the assignment run idempotent and blocks double-assignment."""

    __tablename__ = "judge_assignments"
    __table_args__ = (UniqueConstraint("submission_id", "judge_id", name="uq_assignment"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="events.id", index=True)
    submission_id: int = Field(foreign_key="submissions.id", index=True)
    judge_id: int = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
