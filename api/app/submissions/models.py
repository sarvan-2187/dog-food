import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from ..timeutil import utcnow


def _ts_column() -> Column:
    """TIMESTAMP WITH TIME ZONE, so the offset survives the round trip."""
    return Column(DateTime(timezone=True), nullable=False)


class SubmissionStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"


class Submission(SQLModel, table=True):
    """One submission per team (PLAN.md: draft/edit endpoints, autosave PATCH)."""

    __tablename__ = "submissions"

    id: Optional[int] = Field(default=None, primary_key=True)
    team_id: int = Field(foreign_key="teams.id", unique=True, index=True)
    event_id: int = Field(foreign_key="events.id", index=True)
    title: str = ""
    description: str = ""
    track: str = ""
    status: SubmissionStatus = Field(default=SubmissionStatus.draft)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
