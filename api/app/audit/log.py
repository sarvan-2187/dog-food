"""Writer and query helpers for the audit log.

`record()` stages a row on the caller's session without committing, so the audit
entry shares the transaction of the action it describes.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlmodel import Session, select

from .models import AuditLog


def record(
    session: Session,
    action: str,
    *,
    actor: Optional[Any] = None,
    entity_type: str = "",
    entity_id: Optional[int] = None,
    **detail: Any,
) -> AuditLog:
    """Stage an audit entry. The caller commits, so the entry and the action it
    describes land together or not at all."""
    entry = AuditLog(
        actor_id=getattr(actor, "id", None),
        actor_role=getattr(getattr(actor, "role", None), "value", "") or "",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail,
    )
    session.add(entry)
    return entry


def entries_for(session: Session, entity_type: str, entity_id: int) -> list[AuditLog]:
    return list(
        session.exec(
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.id)
        )
    )


def recent(session: Session, limit: int = 100, action: str | None = None) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return list(session.exec(stmt))
