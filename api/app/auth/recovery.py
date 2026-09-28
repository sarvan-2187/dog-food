"""Password recovery (PLAN.md Phase 9).

Every reset link - emailed (9.2), organizer-issued (9.4) or printed by the CLI
(9.6) - is one row in `password_resets`, redeemed through the same two
endpoints and the same /reset/:token page. Only the token's SHA-256 is stored.
"""
from __future__ import annotations

import hashlib
import html
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlmodel import Session, select

from ..audit.log import record
from ..db import get_session
from ..timeutil import utcnow
from ..ratelimit import reset_issue_limiter
from . import mailer
from .deps import require_role
from .models import PasswordReset, ResetChannel, Role, User, UserPublic, find_user_by_email
from .security import hash_password

router = APIRouter(tags=["recovery"])

EMAIL_TTL = timedelta(minutes=30)
HANDOVER_TTL = timedelta(minutes=60)  # organizer and CLI links: handed over live

# Who may issue a reset link for whom (PLAN.md 9.4). Strictly downward: no
# lateral takeover between organizers, and nobody resets an admin from the UI.
MAY_RESET: dict[Role, frozenset[Role]] = {
    Role.organizer: frozenset({Role.participant, Role.judge}),
    Role.admin: frozenset({Role.participant, Role.judge, Role.organizer}),
}


def validate_new_password(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters.")
    return v


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def reset_url(token: str) -> str:
    return f"{mailer.APP_BASE_URL}/reset/{token}"


def _first_name(user: User) -> str:
    return user.name.split()[0] if user.name.strip() else "there"


def issue_reset(
    session: Session,
    user: User,
    channel: ResetChannel,
    *,
    issued_by: Optional[User] = None,
) -> tuple[str, PasswordReset]:
    """Create a link for `user`, retiring any earlier unused one. Stages rows on
    the caller's session; the caller commits. Returns (raw token, row)."""
    now = utcnow()
    for old in session.exec(
        select(PasswordReset).where(
            PasswordReset.user_id == user.id,
            PasswordReset.used_at.is_(None),  # type: ignore[union-attr]
            PasswordReset.expires_at > now,
        )
    ):
        old.expires_at = now
        session.add(old)

    token = secrets.token_urlsafe(32)
    row = PasswordReset(
        user_id=user.id,
        token_hash=_hash(token),
        channel=channel,
        issued_by_id=issued_by.id if issued_by else None,
        expires_at=now + (EMAIL_TTL if channel == ResetChannel.email else HANDOVER_TTL),
    )
    session.add(row)
    session.flush()
    record(
        session,
        "password_reset.issued",
        actor=issued_by,
        entity_type="user",
        entity_id=user.id,
        channel=channel.value,
    )
    return token, row


def _lookup(session: Session, token: str) -> tuple[Optional[PasswordReset], str]:
    """(row, reason). reason is "" for a usable link, else unknown/expired/used."""
    row = session.exec(select(PasswordReset).where(PasswordReset.token_hash == _hash(token))).first()
    if row is None:
        return None, "unknown"
    if row.used_at is not None:
        return row, "used"
    if row.expires_at <= utcnow():
        return row, "expired"
    return row, ""


# --------------------------------------------------------------------------
# Emails. Plain text first, a minimal HTML twin, no remote images or tracking.
# --------------------------------------------------------------------------

def _html(paragraphs: list[str], link: Optional[str] = None, link_label: str = "", footnote: str = "") -> str:
    body = "".join(f'<p style="margin:0 0 16px">{p}</p>' for p in paragraphs)
    if link:
        safe = html.escape(link)
        body += (
            f'<p style="margin:24px 0"><a href="{safe}" '
            'style="background:#1F2426;color:#ffffff;padding:12px 20px;border-radius:6px;'
            f'text-decoration:none;display:inline-block">{html.escape(link_label)}</a></p>'
            '<p style="margin:0 0 16px;color:#5b6166;font-size:13px">'
            f"Or paste this link into your browser:<br>{safe}</p>"
        )
    if footnote:
        body += f'<p style="margin:16px 0 0;color:#5b6166;font-size:13px">{html.escape(footnote)}</p>'
    return (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;font-size:15px;'
        f'line-height:1.5;color:#1F2426;max-width:520px">{body}'
        '<p style="margin:24px 0 0;color:#5b6166;font-size:13px">- HackFlow</p></div>'
    )


def reset_email(user: User, token: str) -> tuple[str, str, str]:
    link = reset_url(token)
    name = _first_name(user)
    ignore = "If you didn't ask for this, you can ignore this email - your password hasn't changed."
    text = (
        f"Hi {name},\n\n"
        "Someone asked to reset the password for your HackFlow account. "
        "If it was you, open this link to choose a new one:\n\n"
        f"{link}\n\n"
        "The link works once and expires in 30 minutes.\n\n"
        f"{ignore}\n\n"
        "- HackFlow\n"
    )
    body = _html(
        [
            f"Hi {html.escape(name)},",
            "Someone asked to reset the password for your HackFlow account. "
            "If it was you, choose a new one below. The link works once and expires in 30 minutes.",
        ],
        link,
        "Choose a new password",
        ignore,
    )
    return "Reset your HackFlow password", text, body


def changed_email(user: User) -> tuple[str, str, str]:
    name = _first_name(user)
    when = utcnow().strftime("%d %b %Y at %H:%M UTC")
    text = (
        f"Hi {name},\n\n"
        f"The password for your HackFlow account was changed on {when}, "
        "and every other device was signed out.\n\n"
        "If this was you, there's nothing else to do.\n\n"
        "If it wasn't you, contact your event organizer straight away - "
        "they can hand the account back to you with a new reset link.\n\n"
        "- HackFlow\n"
    )
    body = _html(
        [
            f"Hi {html.escape(name)},",
            f"The password for your HackFlow account was changed on {html.escape(when)}, "
            "and every other device was signed out.",
            "If this was you, there's nothing else to do.",
            "<strong>If it wasn't you</strong>, contact your event organizer straight away - "
            "they can hand the account back to you with a new reset link.",
        ]
    )
    return "Your HackFlow password was changed", text, body


def queue_changed_email(background_tasks: BackgroundTasks, user: User) -> None:
    if mailer.CONFIG.enabled:
        background_tasks.add_task(mailer.send_quietly, user.email, *changed_email(user))


# --------------------------------------------------------------------------
# Redeeming a link - shared by every channel.
# --------------------------------------------------------------------------

class ResetPreview(BaseModel):
    valid: bool
    reason: str = ""  # "" | "unknown" | "expired" | "used"
    first_name: Optional[str] = None
    email_enabled: bool


class RedeemRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_len(cls, v: str) -> str:
        return validate_new_password(v)


class RedeemResult(BaseModel):
    user: UserPublic
    issued_by_name: Optional[str] = None


@router.get("/api/password-resets/{token}/preview", response_model=ResetPreview)
def preview_reset(token: str, session: Session = Depends(get_session)) -> ResetPreview:
    """Never consumes the link: mail scanners open links to check them, and a
    link spent on that GET would be dead before the person clicks it."""
    row, reason = _lookup(session, token)
    first_name = None
    if row is not None and not reason:
        user = session.get(User, row.user_id)
        first_name = _first_name(user) if user else None
    return ResetPreview(valid=not reason, reason=reason, first_name=first_name, email_enabled=mailer.CONFIG.enabled)


@router.post("/api/password-resets/{token}/redeem", response_model=RedeemResult)
def redeem_reset(
    token: str,
    payload: RedeemRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> RedeemResult:
    from .router import public_user, set_session_cookie  # router imports this module

    row, reason = _lookup(session, token)
    user = session.get(User, row.user_id) if row is not None and not reason else None
    if user is None:
        message = {
            "used": "This reset link has already been used.",
            "expired": "This reset link has expired.",
        }.get(reason, "This reset link isn't valid.")
        raise HTTPException(status.HTTP_410_GONE, message)

    user.password_hash = hash_password(payload.new_password)
    user.session_version += 1
    row.used_at = utcnow()
    session.add(user)
    session.add(row)
    record(
        session, "password_reset.redeemed", actor=user, entity_type="user", entity_id=user.id, channel=row.channel.value
    )
    session.commit()
    session.refresh(user)

    set_session_cookie(response, user)
    queue_changed_email(background_tasks, user)
    issuer = session.get(User, row.issued_by_id) if row.issued_by_id else None
    return RedeemResult(user=public_user(session, user), issued_by_name=issuer.name if issuer else None)


# --------------------------------------------------------------------------
# Organizer-issued links (9.4) - the fallback when email is off or bounced.
# --------------------------------------------------------------------------

class IssueRequest(BaseModel):
    email: EmailStr


class IssuedLink(BaseModel):
    url: str
    expires_at: datetime
    name: str
    email: str
    role: Role


def _article(word: str) -> str:
    return "an" if word[:1] in "aeiou" else "a"


@router.post("/api/password-resets", response_model=IssuedLink, status_code=status.HTTP_201_CREATED)
def create_reset_link(
    payload: IssueRequest,
    issuer: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> IssuedLink:
    """The raw link exists in this one response and nowhere else. An organizer
    looking an email up is not an enumeration leak: users.csv already lists
    every address to them."""
    target = find_user_by_email(session, payload.email)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No HackFlow account uses that email address.")
    if target.id == issuer.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "That's your own account - change your password from your profile instead."
        )
    if target.role not in MAY_RESET.get(issuer.role, frozenset()):
        role = target.role.value
        hint = " Only an admin can reset an organizer." if target.role == Role.organizer else ""
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"You can't create a reset link for {_article(role)} {role} account.{hint}"
        )
    # Charged only for links actually issued - a typo'd email isn't a link.
    allowed, retry_after = reset_issue_limiter.check(f"issue:{issuer.id}")
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "You've created a lot of reset links in the last hour - "
            f"try again in about {max(1, round(retry_after / 60))} minutes.",
        )
    token, row = issue_reset(session, target, ResetChannel.organizer, issued_by=issuer)
    session.commit()
    return IssuedLink(
        url=reset_url(token), expires_at=row.expires_at, name=target.name, email=target.email, role=target.role
    )


# --------------------------------------------------------------------------
# Admin "Email delivery" card (9.3). Never returns SMTP_PASSWORD.
# --------------------------------------------------------------------------

class EmailStatus(BaseModel):
    enabled: bool
    host: str
    port: int
    security: str
    sender: str
    username_set: bool
    base_url: str


@router.get("/api/admin/email", response_model=EmailStatus)
def email_status(_: User = Depends(require_role(Role.admin))) -> EmailStatus:
    cfg = mailer.CONFIG
    return EmailStatus(
        enabled=cfg.enabled,
        host=cfg.host,
        port=cfg.port,
        security=cfg.security,
        sender=cfg.sender,
        username_set=bool(cfg.username),
        base_url=mailer.APP_BASE_URL,
    )


class TestEmailResult(BaseModel):
    sent_to: str


@router.post("/api/admin/email/test", response_model=TestEmailResult)
def send_test_email(admin: User = Depends(require_role(Role.admin))) -> TestEmailResult:
    """Synchronous on purpose: the admin is watching for the result, and the
    whole point is to surface the server's error in plain language."""
    if not mailer.CONFIG.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is off - set SMTP_HOST and restart the api container.")
    line = "This is a test from HackFlow. If you can read it, password reset emails will work."
    try:
        mailer.send(admin.email, "HackFlow test email", f"{line}\n\n- HackFlow\n", _html([line]))
    except mailer.MailError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return TestEmailResult(sent_to=admin.email)
