"""Read-only audit queries for organizers (PLAN.md section 2).

There is deliberately no write, update or delete endpoint: the log is
append-only, and the only way a row appears is as a side effect of the action it
records.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import Role, User, require_role
from ..db import get_session
from .models import AuditLog

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditEntry(BaseModel):
    id: int
    actor_id: Optional[int]
    actor_name: str
    actor_role: str
    action: str
    entity_type: str
    entity_id: Optional[int]
    detail: Dict[str, Any]
    created_at: datetime


@router.get("", response_model=list[AuditEntry])
def list_entries(
    action: "str | None" = Query(default=None),
    entity_type: "str | None" = Query(default=None),
    entity_id: "int | None" = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> list[AuditEntry]:
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)

    out: list[AuditEntry] = []
    for row in session.exec(stmt):
        actor = session.get(User, row.actor_id) if row.actor_id else None
        out.append(
            AuditEntry(
                id=row.id,
                actor_id=row.actor_id,
                actor_name=actor.name if actor else "Anonymous",
                actor_role=row.actor_role,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                detail=row.detail,
                created_at=row.created_at,
            )
        )
    return out
