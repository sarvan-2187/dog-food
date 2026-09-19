"""Admin user management (PLAN.md Phase 10.10).

Before this, organizer accounts could only come from fixtures/users.json - a
real organization had no way to add an organizer without editing the database.
Admins can now find accounts, move them between participant / judge /
organizer, and deactivate them. The admin role itself is never granted here:
only the seed data or the break-glass CLI (9.6) makes admins, so a compromised
admin session can't mint more of them, and nobody can lock out an admin.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, or_
from sqlmodel import Session, select

from ..audit.log import record
from ..db import duplicate_team_memberships, get_session
from .deps import require_role
from .models import Role, User

router = APIRouter(prefix="/api/admin", tags=["admin"])

PAGE_SIZE = 50


class AdminUser(BaseModel):
    id: int
    name: str
    email: str
    role: Role
    is_active: bool
    created_at: datetime


class UserPage(BaseModel):
    users: list[AdminUser]
    total: int
    page: int
    page_size: int


def _admin_user(u: User) -> AdminUser:
    return AdminUser(id=u.id, name=u.name, email=u.email, role=u.role, is_active=u.is_active, created_at=u.created_at)


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/users", response_model=UserPage)
def list_users(
    q: Optional[str] = Query(default=None, max_length=100),
    role: Optional[Role] = Query(default=None),
    page: int = Query(default=1, ge=1),
    _: User = Depends(require_role(Role.admin)),
    session: Session = Depends(get_session),
) -> UserPage:
    stmt = select(User)
    if q and q.strip():
        like = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(or_(User.name.ilike(like, escape="\\"), User.email.ilike(like, escape="\\")))
    if role is not None:
        stmt = stmt.where(User.role == role)
    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = session.exec(stmt.order_by(User.name, User.id).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE))
    return UserPage(users=[_admin_user(u) for u in rows], total=total, page=page, page_size=PAGE_SIZE)


class UserChange(BaseModel):
    role: Optional[Role] = None
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def not_admin(cls, v: Optional[Role]) -> Optional[Role]:
        if v == Role.admin:
            raise ValueError("The admin role can't be granted from here.")
        return v


@router.patch("/users/{user_id}", response_model=AdminUser)
def change_user(
    user_id: int,
    payload: UserChange,
    admin: User = Depends(require_role(Role.admin)),
    session: Session = Depends(get_session),
) -> AdminUser:
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if target.id == admin.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't change your own role or deactivate yourself.")
    if target.role == Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin accounts can't be changed or deactivated from here.")

    if payload.role is not None and payload.role != target.role:
        previous = target.role
        target.role = payload.role
        record(
            session,
            "user.role_changed",
            actor=admin,
            entity_type="user",
            entity_id=target.id,
            previous_role=previous.value,
            role=target.role.value,
        )
    if payload.is_active is not None and payload.is_active != target.is_active:
        target.is_active = payload.is_active
        if not target.is_active:
            # Ends every session at once, not at the next cookie expiry.
            target.session_version += 1
        record(
            session,
            "user.deactivated" if not target.is_active else "user.reactivated",
            actor=admin,
            entity_type="user",
            entity_id=target.id,
        )
    session.add(target)
    session.commit()
    session.refresh(target)
    return _admin_user(target)


class DuplicateMembership(BaseModel):
    event_id: int
    event_name: str
    user_id: int
    user_name: str
    teams: int


@router.get("/integrity", response_model=list[DuplicateMembership])
def integrity(
    _: User = Depends(require_role(Role.admin)),
    session: Session = Depends(get_session),
) -> list[DuplicateMembership]:
    """People on more than one team in one event - only possible in data
    written before PLAN.md 10.2. Listed on the admin dashboard until resolved
    with the team leave/remove controls (10.9)."""
    from ..events.models import Event

    out: list[DuplicateMembership] = []
    for event_id, user_id, count in duplicate_team_memberships():
        event = session.get(Event, event_id)
        user = session.get(User, user_id)
        out.append(
            DuplicateMembership(
                event_id=event_id,
                event_name=event.name if event else "",
                user_id=user_id,
                user_name=user.name if user else "",
                teams=count,
            )
        )
    return out
