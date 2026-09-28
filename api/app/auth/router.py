"""Register / login / logout / me."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlmodel import Session, select

from ..audit.log import record
from ..db import get_session
from ..storage.lookup import image_url_for
from .deps import get_current_user
from .models import Role, User, UserPublic
from .security import hash_password, verify_password
from .session import SESSION_COOKIE_NAME, SESSION_MAX_AGE, create_session_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public(session: Session, user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        avatar_url=image_url_for(session, "user", user.id),
    )


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str

    @field_validator("password")
    @classmethod
    def password_len(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v

    @field_validator("name")
    @classmethod
    def name_len(cls, v: str) -> str:
        v = v.strip()
        if not (2 <= len(v) <= 60):
            raise ValueError("Name must be 2-60 characters.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _set_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_token(user_id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, session: Session = Depends(get_session)) -> UserPublic:
    """Public sign-up always creates a participant. Judge/organizer/admin accounts
    are seeded from fixtures only (PLAN.md Open Questions)."""
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(
        email=payload.email,
        name=payload.name,
        password_hash=hash_password(payload.password),
        role=Role.participant,
    )
    session.add(user)
    session.flush()
    record(session, "user.registered", actor=user, entity_type="user", entity_id=user.id)
    session.commit()
    session.refresh(user)
    _set_session_cookie(response, user.id)
    return _public(session, user)


@router.post("/login", response_model=UserPublic)
def login(payload: LoginRequest, response: Response, session: Session = Depends(get_session)) -> UserPublic:
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    record(session, "user.logged_in", actor=user, entity_type="user", entity_id=user.id)
    session.commit()
    _set_session_cookie(response, user.id)
    return _public(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME)


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> UserPublic:
    return _public(session, user)
