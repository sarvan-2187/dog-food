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


class UserPublic(SQLModel):
    """Response shape - never leaks password_hash."""

    id: int
    email: str
    name: str
    role: Role
    avatar_url: Optional[str] = None
