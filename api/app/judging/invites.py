"""Judge invitation — the only route into the `judge` role.

PLAN.md T2's first clause is "judge invitation and assignment". `judge` has no
self-service signup on purpose: a self-serve judge account would grant sight of
every score in the event to anyone who asked. So an organizer or admin issues a
single-use, expiring invitation, and redemption promotes the signed-in account.

Both conditions (single-use, unexpired) are enforced here, server-side. The UI
hiding a stale link is not a control.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, get_current_user, require_role
from ..db import get_session
from ..timeutil import utcnow
from .models import JudgeInvite

router = APIRouter(prefix="/api/judge-invites", tags=["judge-invites"])

ORGANIZER = (Role.organizer, Role.admin)


class InviteCreate(BaseModel):
    invited_email: Optional[EmailStr] = None
    note: str = ""
    expires_in_days: int = 14

    @field_validator("expires_in_days")
    @classmethod
    def days_range(cls, v: int) -> int:
        if not (1 <= v <= 90):
            raise ValueError("An invitation must expire between 1 and 90 days from now.")
        return v

    @field_validator("note")
    @classmethod
    def note_len(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 200:
            raise ValueError("Note must be 200 characters or fewer.")
        return v


class InvitePublic(BaseModel):
    id: int
    token: str
    invited_email: str
    note: str
    expires_at: datetime
    redeemed_at: Optional[datetime]
    redeemed_by_name: Optional[str]
    status: str  # "open" | "redeemed" | "expired"


class InvitePreview(BaseModel):
    """What the redemption page needs before it does anything.

    Carries no token-holder identity and nothing about the event, so handing the
    link to the wrong person leaks nothing beyond "this is a judge invitation".
    """

    valid: bool
    reason: str = ""
    expires_at: Optional[datetime] = None


class RedeemResult(BaseModel):
    role: Role
    already_a_judge: bool


def _status(invite: JudgeInvite) -> str:
    if invite.redeemed_at is not None:
        return "redeemed"
    if invite.expires_at < utcnow():
        return "expired"
    return "open"


def _public(session: Session, invite: JudgeInvite) -> InvitePublic:
    redeemer = session.get(User, invite.redeemed_by_id) if invite.redeemed_by_id else None
    return InvitePublic(
        id=invite.id,
        token=invite.token,
        invited_email=invite.invited_email,
        note=invite.note,
        expires_at=invite.expires_at,
        redeemed_at=invite.redeemed_at,
        redeemed_by_name=redeemer.name if redeemer else None,
        status=_status(invite),
    )


@router.post("", response_model=InvitePublic, status_code=status.HTTP_201_CREATED)
def create_invite(
    payload: InviteCreate,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> InvitePublic:
    invite = JudgeInvite(
        invited_email=str(payload.invited_email) if payload.invited_email else "",
        note=payload.note,
        created_by_id=user.id,
        expires_at=utcnow() + timedelta(days=payload.expires_in_days),
    )
    session.add(invite)
    session.flush()
    record(
        session,
        "judge_invite.created",
        actor=user,
        entity_type="judge_invite",
        entity_id=invite.id,
        invited_email=invite.invited_email,
    )
    session.commit()
    session.refresh(invite)
    return _public(session, invite)


@router.get("", response_model=list[InvitePublic])
def list_invites(
    _: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> list[InvitePublic]:
    invites = session.exec(select(JudgeInvite).order_by(JudgeInvite.id.desc())).all()
    return [_public(session, i) for i in invites]


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(
    invite_id: int,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> None:
    invite = session.get(JudgeInvite, invite_id)
    if not invite:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found.")
    if invite.redeemed_at is not None:
        # Revoking a redeemed invitation would imply it un-judges the person, which it
        # does not. Say so rather than appearing to do something.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This invitation has already been used, so revoking it would change nothing. "
            "Change that person's role directly instead.",
        )
    record(session, "judge_invite.revoked", actor=user, entity_type="judge_invite", entity_id=invite_id)
    session.delete(invite)
    session.commit()


@router.get("/{token}/preview", response_model=InvitePreview)
def preview_invite(token: str, session: Session = Depends(get_session)) -> InvitePreview:
    """Public, so the redemption page can explain a dead link instead of failing
    at the moment someone clicks accept."""
    invite = session.exec(select(JudgeInvite).where(JudgeInvite.token == token)).first()
    if not invite:
        return InvitePreview(valid=False, reason="That invitation link is not valid.")
    if invite.redeemed_at is not None:
        return InvitePreview(valid=False, reason="That invitation has already been used.")
    if invite.expires_at < utcnow():
        return InvitePreview(valid=False, reason="That invitation has expired.")
    return InvitePreview(valid=True, expires_at=invite.expires_at)


@router.post("/{token}/redeem", response_model=RedeemResult)
def redeem_invite(
    token: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RedeemResult:
    """Promote the signed-in account to `judge`.

    Requires a session: the invitation grants a role to a *person*, so there has to
    be an account to grant it to. The frontend sends people through login/register
    first with a `next` back to here.
    """
    invite = session.exec(select(JudgeInvite).where(JudgeInvite.token == token)).first()
    if not invite:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That invitation link is not valid.")

    # Already a judge: succeed without burning the invitation, so a double-click or a
    # refresh is harmless and the organizer's invite is not silently consumed.
    if user.role == Role.judge:
        return RedeemResult(role=user.role, already_a_judge=True)

    # Refuse rather than demote. An organizer redeeming a judge link would otherwise
    # lose the ability to run their own event, with no warning.
    if user.role in ORGANIZER:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You are signed in as an {user.role.value}. Accepting this would replace that "
            "with the judge role and remove your ability to run events, so it has been left "
            "alone - sign in as the account that should judge, then open the link again.",
        )

    if invite.redeemed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That invitation has already been used.")
    if invite.expires_at < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That invitation has expired.")

    previous = user.role
    user.role = Role.judge
    invite.redeemed_at = utcnow()
    invite.redeemed_by_id = user.id
    session.add(user)
    session.add(invite)
    record(
        session,
        "judge_invite.redeemed",
        actor=user,
        entity_type="judge_invite",
        entity_id=invite.id,
        previous_role=previous.value,
    )
    session.commit()
    session.refresh(user)
    return RedeemResult(role=user.role, already_a_judge=False)
