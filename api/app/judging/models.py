"""Rubrics and judge assignments (PLAN.md Phase 2, section 8)."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from ..timeutil import utcnow


def _ts_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False)


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
