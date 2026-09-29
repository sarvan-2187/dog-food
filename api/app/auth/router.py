"""Register / login / logout / me, plus the signed-in and self-service halves
of password recovery (PLAN.md Phase 9)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, EmailStr, field_validator
from sqlmodel import Session, select

from ..audit.log import record
from ..db import get_session
from ..storage.lookup import image_url_for
from ..ratelimit import (
    forgot_email_limiter,
    forgot_ip_limiter,
    login_account_limiter,
    login_ip_limiter,
    register_ip_limiter,
    verify_email_limiter,
)
from ..timeutil import utcnow
from . import mailer
from .deps import get_current_user
from .models import ResetChannel, Role, User, UserPublic, find_user_by_email
from .recovery import issue_reset, queue_changed_email, reset_email, validate_new_password
from .security import hash_password, verify_password
from .session import SESSION_COOKIE_NAME, SESSION_MAX_AGE, SESSION_SECRET, create_session_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


def public_user(session: Session, user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        avatar_url=image_url_for(session, "user", user.id),
        email_verified=user.email_verified_at is not None,
    )


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str

    @field_validator("password")
    @classmethod
    def password_len(cls, v: str) -> str:
        return validate_new_password(v)

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


def set_session_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_token(user.id, user.session_version),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, request: Request, response: Response, session: Session = Depends(get_session)
) -> UserPublic:
    """Public sign-up always creates a participant. Judge/organizer/admin accounts
    are seeded from fixtures only (PLAN.md Open Questions)."""
    allowed, retry_after = register_ip_limiter.check(f"register-ip:{request.client.host if request.client else 'unknown'}")
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many sign-ups from this network. Try again in about {max(1, round(retry_after / 60))} minutes.",
            headers={"Retry-After": str(max(1, round(retry_after)))},
        )
    existing = find_user_by_email(session, payload.email)
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(
        email=payload.email.strip().lower(),
        name=payload.name,
        password_hash=hash_password(payload.password),
        role=Role.participant,
    )
    session.add(user)
    session.flush()
    record(session, "user.registered", actor=user, entity_type="user", entity_id=user.id)
    session.commit()
    session.refresh(user)
    set_session_cookie(response, user)
    return public_user(session, user)


# Checked against when the email has no account, so an unknown address costs the
# same bcrypt time as a known one and response timing can't reveal which emails
# are registered (PLAN.md 10.4).
_DUMMY_HASH = hash_password("no-account-has-this-password")


def _throttled(retry_after: float) -> HTTPException:
    minutes = max(1, round(retry_after / 60))
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Too many attempts. Try again in about {minutes} minute{'s' if minutes != 1 else ''}, or reset your password.",
    )


@router.post("/login", response_model=UserPublic)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> UserPublic:
    """Only failed attempts count - 10 per account, 30 per IP, per 15 minutes -
    and a throttled attempt is refused before the password is even checked. The
    account key is the typed email, so the answer is identical whether or not
    that account exists."""
    account_key = f"login-account:{payload.email.lower()}"
    ip_key = f"login-ip:{request.client.host if request.client else 'unknown'}"
    for limiter, key in ((login_account_limiter, account_key), (login_ip_limiter, ip_key)):
        allowed, retry_after = limiter.peek(key)
        if not allowed:
            raise _throttled(retry_after)

    user = find_user_by_email(session, payload.email)
    password_ok = verify_password(payload.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not password_ok:
        account_ok, account_retry = login_account_limiter.check(account_key)
        ip_ok, ip_retry = login_ip_limiter.check(ip_key)
        if not (account_ok and ip_ok):
            # Recorded once, as the limit is reached - later attempts stop at
            # the peek above without touching the log.
            record(session, "user.login_throttled", entity_type="user", entity_id=user.id if user else None, ip=ip_key[9:])
            session.commit()
            raise _throttled(max(account_retry, ip_retry))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated. Contact an admin.")
    login_account_limiter.forget(account_key)
    record(session, "user.logged_in", actor=user, entity_type="user", entity_id=user.id)
    session.commit()
    set_session_cookie(response, user)
    return public_user(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME)


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> UserPublic:
    return public_user(session, user)


# --------------------------------------------------------------------------
# Password recovery (PLAN.md Phase 9)
# --------------------------------------------------------------------------

class RecoveryOptions(BaseModel):
    email: bool


@router.get("/recovery-options", response_model=RecoveryOptions)
def recovery_options() -> RecoveryOptions:
    """Lets /forgot-password show the email form or, with email off, point the
    person at an organizer instead of pretending to send something."""
    return RecoveryOptions(email=mailer.CONFIG.enabled)


class ForgotRequest(BaseModel):
    email: EmailStr


class ForgotResult(BaseModel):
    message: str


FORGOT_MESSAGE = "If an account exists for that address, we've sent a reset link. It expires in 30 minutes."


@router.post("/forgot-password", response_model=ForgotResult)
def forgot_password(
    payload: ForgotRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> ForgotResult:
    """Identical answer whether or not the account exists, and whether or not a
    rate limit was hit, so this endpoint can't be used to learn who has an
    account. The email goes out in the background, so the response never waits
    on the mail server either."""
    if not mailer.CONFIG.enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Password reset emails aren't set up here. Ask an organizer for a reset link.",
        )
    email = payload.email.lower()
    ip = request.client.host if request.client else "unknown"
    # Both buckets are always charged, so a flood from one IP can't hide behind
    # rotating addresses and a flood at one address can't hide behind IPs.
    ip_ok, _ = forgot_ip_limiter.check(f"forgot-ip:{ip}")
    email_ok, _ = forgot_email_limiter.check(f"forgot-email:{email}")
    if ip_ok and email_ok:
        user = find_user_by_email(session, payload.email)
        if user is not None:
            token, _row = issue_reset(session, user, ResetChannel.email)
            session.commit()
            background_tasks.add_task(mailer.send_quietly, user.email, *reset_email(user, token))
    return ForgotResult(message=FORGOT_MESSAGE)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_len(cls, v: str) -> str:
        return validate_new_password(v)


@router.post("/password", response_model=UserPublic)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserPublic:
    """Signs the account out everywhere else; this device gets a fresh cookie."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is incorrect.")
    user.password_hash = hash_password(payload.new_password)
    user.session_version += 1
    session.add(user)
    record(session, "user.password_changed", actor=user, entity_type="user", entity_id=user.id)
    session.commit()
    session.refresh(user)
    set_session_cookie(response, user)
    queue_changed_email(background_tasks, user)
    return public_user(session, user)


class NameChange(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_len(cls, v: str) -> str:
        v = v.strip()
        if not (2 <= len(v) <= 60):
            raise ValueError("Name must be 2-60 characters.")
        return v


@router.patch("/me", response_model=UserPublic)
def change_name(
    payload: NameChange,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserPublic:
    """PLAN.md 10.13. Names are read live everywhere they appear, so nothing
    else needs rewriting. Email changes are out of scope: they need the new
    address verified first."""
    old = user.name
    user.name = payload.name
    session.add(user)
    record(session, "user.renamed", actor=user, entity_type="user", entity_id=user.id, old_name=old, name=user.name)
    session.commit()
    session.refresh(user)
    return public_user(session, user)


# --------------------------------------------------------------------------
# Email verification (THREAT-MODEL entry 25). A stateless signed link, like the
# voter email link: nothing is stored until it is followed.
# --------------------------------------------------------------------------

_verify_link = URLSafeTimedSerializer(SESSION_SECRET, salt="dogfood-verify-email")
VERIFY_LINK_MAX_AGE = 24 * 3600


class VerifySent(BaseModel):
    sent_to: str


@router.post("/verify-email", response_model=VerifySent)
def send_verification(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> VerifySent:
    if not mailer.CONFIG.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email isn't set up here, so addresses can't be verified.")
    if user.email_verified_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Your email is already verified.")
    allowed, retry_after = verify_email_limiter.check(f"verify:{user.id}")
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"A link was sent recently - try again in about {max(1, round(retry_after / 60))} minutes.",
        )
    token = _verify_link.dumps({"u": user.id, "m": user.email.lower()})
    link = f"{mailer.APP_BASE_URL}/api/auth/verify-email/confirm?token={token}"
    text = f"Confirm this address for your HackFlow account:\n\n{link}\n\nThe link works for 24 hours.\n\n- HackFlow\n"
    background_tasks.add_task(mailer.send_quietly, user.email, "Confirm your email - HackFlow", text)
    return VerifySent(sent_to=user.email)


@router.get("/verify-email/confirm")
def confirm_verification(token: str, session: Session = Depends(get_session)) -> RedirectResponse:
    try:
        data = _verify_link.loads(token, max_age=VERIFY_LINK_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return RedirectResponse("/profile?verified=0", status_code=status.HTTP_303_SEE_OTHER)
    user = session.get(User, data["u"])
    # The address must still be the one the link was sent to.
    if user is None or user.email.lower() != data["m"]:
        return RedirectResponse("/profile?verified=0", status_code=status.HTTP_303_SEE_OTHER)
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
        session.add(user)
        record(session, "user.email_verified", actor=user, entity_type="user", entity_id=user.id)
        session.commit()
    return RedirectResponse("/profile?verified=1", status_code=status.HTTP_303_SEE_OTHER)
