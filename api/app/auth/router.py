"""Register / login / logout / me."""
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlmodel import Session, select

from ..audit.log import record
from ..db import get_session
from ..ratelimit import login_account_limiter, login_ip_limiter
from ..storage.lookup import image_url_for
from .deps import get_current_user
from .models import Role, User, UserPublic
from .security import hash_password, verify_password
from .session import SESSION_COOKIE_NAME, SESSION_MAX_AGE, create_session_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_key(request: Request) -> str:
    """Hashed, so throttling sign-in does not turn the process into a log of
    everyone's IP address. Same treatment the voting endpoints already give it."""
    client = request.client.host if request.client else ""
    agent = request.headers.get("user-agent", "")
    return hashlib.sha256(f"{client}|{agent}".encode()).hexdigest()[:32]


def _too_many(retry_after: float) -> HTTPException:
    wait = max(1, round(retry_after))
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Too many sign-in attempts. Please wait about {wait} seconds and try again.",
        headers={"Retry-After": str(wait)},
    )


def _account_key(email: str) -> str:
    return f"login-account:{email.strip().lower()}"


def _throttle_login(email: str) -> None:
    """Phase 10.4, charged before the password is checked.

    Spending the budget first, and wording the refusal identically either way,
    keeps the limiter from becoming an account-enumeration oracle: an unknown
    address must behave exactly like a known one with the wrong password.
    """
    allowed, retry_after = login_account_limiter.check(_account_key(email))
    if not allowed:
        raise _too_many(retry_after)


def _charge_failure(request: Request) -> None:
    """Charge one failure to this client. Only failures are counted here -- see
    the note on the limiter itself for why successful sign-ins are not."""
    allowed, retry_after = login_ip_limiter.check(f"login-ip:{_client_key(request)}")
    if not allowed:
        raise _too_many(retry_after)


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
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> UserPublic:
    _throttle_login(payload.email)
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        record(session, "user.login_failed", actor=None, entity_type="user", entity_id=None, email=payload.email)
        session.commit()
        _charge_failure(request)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    # A clean sign-in clears this account's budget, so a person who mistyped
    # twice and then got it right is not still carrying those two failures.
    login_account_limiter.reset_key(_account_key(payload.email))
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
