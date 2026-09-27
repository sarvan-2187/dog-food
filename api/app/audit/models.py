"""Append-only audit log (PLAN.md section 2, wired up in Phase 3).

Append-only is a property of how this table is *used*, not something Postgres
enforces here: there is no update or delete path anywhere in the app, and no
endpoint that can mutate a row once written. Rows are written on the same
session as the action they describe, so an action and its audit entry commit or
roll back together -- a logged action that did not happen would be worse than no
log at all.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

from ..timeutil import utcnow


def _ts_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Nullable: some actions are anonymous, and the log should record that
    # honestly rather than attribute them to nobody-in-particular as user 0.
    actor_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    actor_role: str = ""
    action: str = Field(index=True)
    entity_type: str = ""
    entity_id: Optional[int] = Field(default=None, index=True)
    detail: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
