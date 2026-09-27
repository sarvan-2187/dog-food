"""User model and the four platform roles (PLAN.md section 1)."""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from ..timeutil import utcnow


def _ts_column() -> Column:
    """TIMESTAMP WITH TIME ZONE, so the offset survives the round trip."""
    return Column(DateTime(timezone=True), nullable=False)


class Role(str, enum.Enum):
    participant = "participant"
    judge = "judge"
    organizer = "organizer"
    admin = "admin"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    name: str
    password_hash: str
    role: Role = Field(default=Role.participant)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
    # Signed into every session cookie and bumped on each password change or
    # reset, so one bump signs the account out everywhere (PLAN.md Phase 9.1).
    session_version: int = Field(default=0)
    # False blocks sign-in and, with a session_version bump, ends every session
    # (PLAN.md Phase 10.10). Admin accounts can't be deactivated.
    is_active: bool = Field(default=True)
    # Set when the owner follows an emailed verification link, or by the seed for
    # fixture accounts. Events can require it to vote (THREAT-MODEL entry 25).
    email_verified_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class ResetChannel(str, enum.Enum):
    email = "email"
    organizer = "organizer"
    cli = "cli"


class PasswordReset(SQLModel, table=True):
    """A single-use reset link (PLAN.md Phase 9). Only the SHA-256 of the token
    is stored, so a database read never yields a working link."""

    __tablename__ = "password_resets"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(unique=True, index=True)
    channel: ResetChannel
    issued_by_id: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
    expires_at: datetime = Field(sa_column=_ts_column())
    used_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


class UserPublic(SQLModel):
    """Response shape - never leaks password_hash."""

    id: int
    email: str
    name: str
    role: Role
    avatar_url: Optional[str] = None
    email_verified: bool = False
