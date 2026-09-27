import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, and_
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
    # Where judges can actually look at the project (PLAN.md Phase 10.5). Optional,
    # http(s) only - validated in SubmissionUpdate - and shown as links, never embedded.
    repo_url: str = ""
    demo_url: str = ""
    video_url: str = ""
    status: SubmissionStatus = Field(default=SubmissionStatus.draft)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
    # Set by an organizer's eligibility decision. A separate column rather than a
    # status value: disqualification is orthogonal to draft/submitted, and
    # reinstating must not lose which of the two it was.
    disqualified_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    disqualified_reason: str = ""

    @property
    def competing(self) -> bool:
        return self.status == SubmissionStatus.submitted and self.disqualified_at is None


def in_competition():
    """SQL twin of `Submission.competing`: submitted and not disqualified. Every
    gallery, voting, assignment and awards query filters on this."""
    return and_(Submission.status == SubmissionStatus.submitted, Submission.disqualified_at.is_(None))
