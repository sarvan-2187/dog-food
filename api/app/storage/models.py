"""Records of uploaded files (PLAN.md Phase 6). Bytes live on disk; only the
record of them lives here -- key, owner, and enough metadata to serve and
validate the file without re-reading it from disk every time."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from ..timeutil import utcnow


def _ts_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False)


class StoredFile(SQLModel, table=True):
    """One row per (owner_type, owner_id): a submission has at most one
    screenshot, a user has at most one avatar. Replacing an image updates
    this same row and deletes the superseded key's bytes, rather than
    orphaning them on disk (PLAN.md Phase 6 UX checklist)."""

    __tablename__ = "stored_files"
    __table_args__ = (UniqueConstraint("owner_type", "owner_id", name="uq_stored_file_owner"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    owner_type: str = Field(index=True)  # "submission" | "user"
    owner_id: int = Field(index=True)
    content_type: str
    size_bytes: int
    checksum: str
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
