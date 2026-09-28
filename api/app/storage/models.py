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
    """One row per (owner_type, owner_id, position): a user has one avatar at
    position 0, and a submission has an image gallery of up to five, in order
    (DOGFOOD T1), where position 0 is its thumbnail. Replacing an image updates
    the same row and deletes the superseded key's bytes, rather than orphaning
    them on disk (PLAN.md Phase 6 UX checklist)."""

    __tablename__ = "stored_files"
    __table_args__ = (
        UniqueConstraint("owner_type", "owner_id", "position", name="uq_stored_file_owner_position"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    owner_type: str = Field(index=True)  # "submission" | "user"
    owner_id: int = Field(index=True)
    position: int = Field(default=0)
    content_type: str
    size_bytes: int
    checksum: str
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
