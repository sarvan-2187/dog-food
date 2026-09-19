import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Column, DateTime, UniqueConstraint, event, text
from sqlmodel import Field, SQLModel

from ..timeutil import utcnow


def _ts_column() -> Column:
    """TIMESTAMP WITH TIME ZONE, so the offset survives the round trip."""
    return Column(DateTime(timezone=True), nullable=False)


def _invite_code() -> str:
    return secrets.token_urlsafe(6)


def _default_expiry() -> datetime:
    return utcnow() + timedelta(days=30)


class Team(SQLModel, table=True):
    __tablename__ = "teams"

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="events.id", index=True)
    name: str
    invite_code: str = Field(default_factory=_invite_code, unique=True, index=True)
    invite_code_expires_at: datetime = Field(default_factory=_default_expiry, sa_column=_ts_column())
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
    # Whoever created the team; may rename it, remove members and hand the role on
    # (PLAN.md Phase 10.9). Null only for a team whose last captain was removed
    # before a successor was set, which the router never leaves in place.
    captain_id: Optional[int] = Field(default=None, foreign_key="users.id")


class TeamMembership(SQLModel, table=True):
    __tablename__ = "team_memberships"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    team_id: int = Field(foreign_key="teams.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    joined_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
    # Denormalised from the team so the database itself can hold "one team per
    # person per event" with a unique index on (event_id, user_id) (PLAN.md 10.2).
    # Filled in automatically below - callers never set it.
    event_id: Optional[int] = Field(default=None, foreign_key="events.id", index=True)


@event.listens_for(TeamMembership, "before_insert")
def _stamp_event_id(_mapper, connection, target: TeamMembership) -> None:
    if target.event_id is None:
        target.event_id = connection.execute(
            text("SELECT event_id FROM teams WHERE id = :t"), {"t": target.team_id}
        ).scalar()
