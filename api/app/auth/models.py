"""User model and the four platform roles (PLAN.md section 1)."""
import enum
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


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
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UserPublic(SQLModel):
    """Response shape - never leaks password_hash."""

    id: int
    email: str
    name: str
    role: Role
