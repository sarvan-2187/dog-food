"""Scores submitted by judges against their assignments (PLAN.md Phase 2)."""
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import JSON, Column, DateTime
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
