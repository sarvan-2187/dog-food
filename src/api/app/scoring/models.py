"""Scores submitted by judges against their assignments (PLAN.md Phase 2)."""
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from ..timeutil import utcnow


def _ts_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False)


class Score(SQLModel, table=True):
    """At most one score per assignment, so re-submitting edits rather than
    stacking duplicates. `values` maps criterion key -> raw value; `raw_total`
    is the weighted total the normalisation pipeline consumes."""

    __tablename__ = "scores"

    id: Optional[int] = Field(default=None, primary_key=True)
    assignment_id: int = Field(foreign_key="judge_assignments.id", unique=True, index=True)
    submission_id: int = Field(foreign_key="submissions.id", index=True)
    judge_id: int = Field(foreign_key="users.id", index=True)
    values: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    comment: str = ""
    raw_total: float = 0.0
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())


class Award(SQLModel, table=True):
    """One configured prize given to one submission (PLAN.md Phase 10.6).
    `prize_rank` is the prize's label from Event.prize_config ("1st Place",
    "Best Developer Tool"). Hidden until results are revealed, like standings."""

    __tablename__ = "awards"
    __table_args__ = (UniqueConstraint("event_id", "prize_rank", name="uq_award_prize"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="events.id", index=True)
    prize_rank: str
    submission_id: int = Field(foreign_key="submissions.id", index=True)
    note: str = ""
    awarded_by_id: int = Field(foreign_key="users.id")
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
