import enum
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


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
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
