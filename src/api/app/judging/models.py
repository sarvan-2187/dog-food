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

    Judge invitations belong to an event (PLAN.md Phase 10.1): redeeming one adds the
    judge to that event's pool, and only that pool is ever assigned its submissions.
    `event_id` is null only on invitations created before 10.1, and on organizer
    invitations (`grants_role == "organizer"`, Phase 10.10), which are platform-wide.
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
    event_id: Optional[int] = Field(default=None, foreign_key="events.id", index=True)
    # "judge" | "organizer". A plain string, not the Role enum, so it can be added to
    # an existing table with one idempotent ALTER (app.db.add_missing_columns).
    grants_role: str = Field(default="judge")


class EventJudge(SQLModel, table=True):
    """A judge's membership of one event's pool (PLAN.md Phase 10.1). Assignment
    draws only from these rows, so a judge brought in for one hackathon is never
    handed another's submissions."""

    __tablename__ = "event_judges"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_judge"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="events.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    added_by_id: Optional[int] = Field(default=None, foreign_key="users.id")
    added_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
    # One of the event's tracks, or None for a judge who takes any track (DOGFOOD
    # T2). A track judge is only ever assigned, shown or allowed to score entries
    # in that track: see judging.assignment.outside_track.
    track: Optional[str] = Field(default=None)


class JudgeConflict(SQLModel, table=True):
    """A judge's declared conflict of interest with one submission (PLAN.md
    Phase 10.7). Assignment treats it exactly like a same-team conflict, so the
    submission is never handed back to that judge on a re-run."""

    __tablename__ = "judge_conflicts"
    __table_args__ = (UniqueConstraint("judge_id", "submission_id", name="uq_judge_conflict"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="events.id", index=True)
    judge_id: int = Field(foreign_key="users.id", index=True)
    submission_id: int = Field(foreign_key="submissions.id", index=True)
    reason: str = ""
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())


class Rubric(SQLModel, table=True):
    """An event may have several of these (e.g. "Technical Rubric",
    "Presentation Rubric") -- see Open Questions. Every submission in the
    event is scored against the COMBINED criteria of all its rubrics, one
    flat criteria list grouped by rubric name on the score form. `criteria`
    is a list of {key, label, weight, max_score}; a criterion key must be
    unique across every rubric in the event (enforced in the router, since
    that's a cross-row check), and the combined weights across the whole
    set must sum to 1.0 before judging can start (checked when judges are
    assigned, not on every individual rubric save, since an organizer
    builds the set up one rubric at a time)."""

    __tablename__ = "rubrics"

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="events.id", index=True)
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
