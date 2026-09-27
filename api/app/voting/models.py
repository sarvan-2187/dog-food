"""Community voting and comments (PLAN.md Phase 3)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from ..timeutil import utcnow


def _ts_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False)


class Vote(SQLModel, table=True):
    """One vote per user per submission.

    The unique constraint is the *hard* guard -- duplicate prevention must not
    depend on application logic that a concurrent request could race past.
    `fingerprint_hash` is the *soft* signal: it flags several accounts voting
    from what looks like one client, which is suspicious but not proof, so it is
    recorded for an organizer to look at rather than used to block silently
    (PLAN.md Phase 3).
    """

    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("user_id", "submission_id", name="uq_vote"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="events.id", index=True)
    submission_id: int = Field(foreign_key="submissions.id", index=True)
    # None for a guest vote (Event.voting_access "open" or "email").
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    # Who voted, for every vote: "email:<hash>" for accounts and confirmed
    # guests, so one address cannot vote once signed in and again as a guest;
    # "anon:<random>" for open-link guests. Unique per submission via the
    # uq_vote_voter index (app.db.add_vote_voter_index).
    voter_key: Optional[str] = Field(default=None, index=True)
    fingerprint_hash: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())


class Comment(SQLModel, table=True):
    __tablename__ = "comments"

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="events.id", index=True)
    submission_id: int = Field(foreign_key="submissions.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    body: str = ""
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
