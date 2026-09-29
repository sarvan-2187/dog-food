"""API keys for third-party integrations.

A browser signs in with a session cookie; a server integrating with HackFlow
(a Discord bot, a CRM sync, a results feed) sends `Authorization: Bearer
hf_...` instead. A key acts as the organizer or admin who created it, through
the same `require_role()` checks as the UI, so a key can never do more than its
owner could by hand, and deactivating the owner kills every key they made.

Only a SHA-256 of the key is stored; the key itself is shown once, at creation.
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import Column, DateTime
from sqlmodel import Field, Session, SQLModel, select

from ..audit.log import record
from ..db import get_session
from ..timeutil import utcnow
from .deps import require_role
from .models import Role, User

PREFIX = "hf_"
MAX_KEYS_PER_USER = 20
# last_used_at is a hint for the owner ("is this key still in use?"), so it is
# only written when stale rather than on every single request.
LAST_USED_GRANULARITY = timedelta(minutes=5)


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str
    # First characters after the prefix, so the owner can tell keys apart.
    hint: str
    key_hash: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))
    last_used_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    revoked_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def user_for_key(session: Session, key: str) -> Optional[User]:
    """The active owner of a live key, or None. Called from auth.deps."""
    if not key.startswith(PREFIX):
        return None
    row = session.exec(select(ApiKey).where(ApiKey.key_hash == hash_key(key), ApiKey.revoked_at.is_(None))).first()
    if row is None:
        return None
    user = session.get(User, row.user_id)
    if user is None or not user.is_active or user.role not in (Role.organizer, Role.admin):
        return None
    now = utcnow()
    if row.last_used_at is None or now - row.last_used_at > LAST_USED_GRANULARITY:
        row.last_used_at = now
        session.add(row)
        session.commit()
    return user


router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])
ORGANIZER = (Role.organizer, Role.admin)


class ApiKeyCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_len(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 60):
            raise ValueError('Give the key a name of 1-60 characters, e.g. "Discord bot".')
        return v


class ApiKeyPublic(BaseModel):
    id: int
    name: str
    hint: str
    created_at: datetime
    last_used_at: Optional[datetime] = None


class ApiKeyCreated(ApiKeyPublic):
    key: str  # shown exactly once


def _public(row: ApiKey) -> ApiKeyPublic:
    return ApiKeyPublic(
        id=row.id, name=row.name, hint=row.hint, created_at=row.created_at, last_used_at=row.last_used_at
    )


@router.get("", response_model=list[ApiKeyPublic])
def list_keys(user: User = Depends(require_role(*ORGANIZER)), session: Session = Depends(get_session)) -> list[ApiKeyPublic]:
    """Your live keys. Never includes the key itself."""
    rows = session.exec(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None)).order_by(ApiKey.id)
    ).all()
    return [_public(r) for r in rows]


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_key(
    payload: ApiKeyCreate,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> ApiKeyCreated:
    live = session.exec(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None))).all()
    if len(live) >= MAX_KEYS_PER_USER:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You already have {MAX_KEYS_PER_USER} keys. Revoke one first.")
    secret = secrets.token_urlsafe(32)
    key = PREFIX + secret
    row = ApiKey(user_id=user.id, name=payload.name, hint=secret[:6], key_hash=hash_key(key))
    session.add(row)
    session.flush()
    record(session, "api_key.created", actor=user, entity_type="api_key", entity_id=row.id, name=row.name)
    session.commit()
    session.refresh(row)
    return ApiKeyCreated(**_public(row).model_dump(), key=key)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(
    key_id: int,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> None:
    row = session.get(ApiKey, key_id)
    # Someone else's key reads as missing, not forbidden: its existence is not yours to know.
    if row is None or row.user_id != user.id or row.revoked_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Key not found.")
    row.revoked_at = utcnow()
    session.add(row)
    record(session, "api_key.revoked", actor=user, entity_type="api_key", entity_id=row.id, name=row.name)
    session.commit()
