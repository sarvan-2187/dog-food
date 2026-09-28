"""Votes and comments (PLAN.md Phase 3)."""
import hashlib

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, get_current_user, get_current_user_optional, mailer
from ..db import get_session
from ..events.models import Event
from ..events.visibility import may_see_results, results_are_public
from ..submissions.models import Submission, SubmissionStatus
from ..teams.models import Team
from ..timeutil import utcnow
from ..webhooks.service import notify
from .models import Comment, Vote
from ..ratelimit import comment_limiter, vote_limiter, voter_email_limiter
from .schemas import CommentPublic, CommentWrite, PublicResultRow, VoteResult
from .voter import (
    EMAIL_LINK_MAX_AGE,
    email_key,
    email_link_token,
    read_email_link_token,
    read_voter_key,
    resolve_voter,
    set_voter_cookie,
)

router = APIRouter(tags=["voting"])


def _client_fingerprint(request: Request) -> str:
    """A coarse client signature: address plus user-agent, hashed.

    Deliberately weak -- it is a *flag*, never a gate. Shared offices and phone
    networks legitimately produce collisions, so blocking on this would lock out
    real voters. The unique constraint is what actually prevents duplicates.
    Hashed rather than stored raw so the audit trail does not become a log of
    everyone's IP address.
    """
    client = request.client.host if request.client else ""
    agent = request.headers.get("user-agent", "")
    return hashlib.sha256(f"{client}|{agent}".encode()).hexdigest()[:32]


def _rate_limit(limiter, key: str, what: str) -> None:
    allowed, retry_after = limiter.check(key)
    if not allowed:
        # A friendly sentence, not a bare 429 (PLAN.md Phase 3 UX). The header is
        # still set for well-behaved clients.
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You've reached the {what} limit for now - try again in about {max(1, round(retry_after))} seconds.",
            headers={"Retry-After": str(max(1, round(retry_after)))},
        )


def _votable_submission(session: Session, submission_id: int) -> tuple[Submission, Event]:
    submission = session.get(Submission, submission_id)
    if not submission or submission.status != SubmissionStatus.submitted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That submission is not in the public gallery.")
    event = session.get(Event, submission.event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That event no longer exists.")
    return submission, event


def _count_votes(session: Session, submission_id: int) -> int:
    return len(session.exec(select(Vote).where(Vote.submission_id == submission_id)).all())


# --------------------------------------------------------------------------
# Voting
# --------------------------------------------------------------------------

@router.post("/api/submissions/{submission_id}/vote", response_model=VoteResult)
def cast_vote(
    submission_id: int,
    request: Request,
    response: Response,
    user: "User | None" = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> VoteResult:
    submission, event = _votable_submission(session, submission_id)
    if not event.voting_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Community voting is not open for this event.")
    user, voter_key = resolve_voter(event, request, response, user, mint=True)
    fingerprint = _client_fingerprint(request)
    # Guests are limited per client, not per cookie: clearing cookies mints a
    # new open-link voter but does not buy a fresh budget.
    _rate_limit(vote_limiter, f"vote:{user.id}" if user else f"vote:fp:{fingerprint}", "voting")

    vote = Vote(
        event_id=event.id,
        submission_id=submission_id,
        user_id=user.id if user else None,
        voter_key=voter_key,
        fingerprint_hash=fingerprint,
    )
    session.add(vote)
    try:
        # The unique constraint is the hard guard: a concurrent double-click
        # cannot slip past a prior SELECT, so let the database decide.
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already voted for this submission.")

    # Soft signal: several voters (accounts or guests) voting from one client.
    # Flagged for an organizer, never used to block (PLAN.md Phase 3).
    others = session.exec(
        select(Vote).where(
            Vote.event_id == event.id,
            Vote.fingerprint_hash == fingerprint,
            Vote.voter_key != voter_key,
        )
    ).all()
    distinct_users = {v.voter_key for v in others}
    if distinct_users:
        record(
            session,
            "vote.duplicate_fingerprint_flagged",
            actor=user,
            entity_type="submission",
            entity_id=submission_id,
            fingerprint_hash=fingerprint,
            other_user_count=len(distinct_users),
        )

    record(
        session,
        "vote.cast",
        actor=user,
        entity_type="submission",
        entity_id=submission_id,
        voter="account" if user else voter_key.split(":", 1)[0],
    )
    session.commit()

    visible = may_see_results(event, user)
    return VoteResult(
        submission_id=submission_id,
        voted=True,
        votes=_count_votes(session, submission_id) if visible else None,
    )


@router.delete("/api/submissions/{submission_id}/vote", response_model=VoteResult)
def withdraw_vote(
    submission_id: int,
    request: Request,
    response: Response,
    user: "User | None" = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> VoteResult:
    submission, event = _votable_submission(session, submission_id)
    if not event.voting_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Community voting is not open for this event.")
    user, voter_key = resolve_voter(event, request, response, user, mint=False)
    mine = Vote.user_id == user.id if user else Vote.voter_key == voter_key
    vote = session.exec(select(Vote).where(Vote.submission_id == submission_id, mine)).first()
    if not vote:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You have not voted for this submission.")
    session.delete(vote)
    record(session, "vote.withdrawn", actor=user, entity_type="submission", entity_id=submission_id)
    session.commit()

    visible = may_see_results(event, user)
    return VoteResult(
        submission_id=submission_id,
        voted=False,
        votes=_count_votes(session, submission_id) if visible else None,
    )


# --------------------------------------------------------------------------
# Guest voters (Event.voting_access "email" / "open")
# --------------------------------------------------------------------------

class VoterEmailRequest(BaseModel):
    email: EmailStr


@router.get("/api/voter/me")
def voter_me(request: Request) -> dict:
    """Which kind of guest voter this browser is, if any: "email", "anon" or
    null. Carries no address - the cookie only holds a hash."""
    key = read_voter_key(request)
    return {"voter": key.split(":", 1)[0] if key else None}


@router.post("/api/events/{event_id}/voter-email", status_code=status.HTTP_202_ACCEPTED)
def request_voter_email(
    event_id: int,
    payload: VoterEmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    event = session.get(Event, event_id)
    if not event or event.status != "published":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    if event.voting_access != "email" or not event.voting_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "This event does not use email-confirmed voting.")
    if not mailer.CONFIG.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is not set up on this HackFlow, so no link can be sent.")
    email = payload.email.strip().lower()
    _rate_limit(voter_email_limiter, f"voter-email:{_client_fingerprint(request)}", "email link")
    _rate_limit(voter_email_limiter, f"voter-email:{email}", "email link")
    link = f"{mailer.APP_BASE_URL}/api/voter-email/confirm?token={email_link_token(event.id, email)}"
    minutes = EMAIL_LINK_MAX_AGE // 60
    background_tasks.add_task(
        mailer.send_quietly,
        email,
        f"Confirm your vote for {event.name}",
        f"Open this link within {minutes} minutes to vote in {event.name}:\n\n{link}\n\n"
        "If you did not ask for it, ignore this email.",
    )
    record(session, "voter.email_link_sent", entity_type="event", entity_id=event.id, voter_key=email_key(email))
    session.commit()
    return {"detail": f"Check your inbox - the link works for {minutes} minutes."}


@router.get("/api/voter-email/confirm")
def confirm_voter_email(token: str, session: Session = Depends(get_session)) -> RedirectResponse:
    """The emailed link. Sets the guest voter cookie and lands on the event's
    gallery. Not single-use: a mail scanner prefetching it grants nothing the
    recipient did not already have."""
    parsed = read_email_link_token(token)
    event = session.get(Event, parsed[0]) if parsed else None
    if parsed is None or event is None:
        return RedirectResponse("/gallery?voter=expired", status.HTTP_303_SEE_OTHER)
    redirect = RedirectResponse(f"/events/{event.slug}/gallery", status.HTTP_303_SEE_OTHER)
    set_voter_cookie(redirect, email_key(parsed[1]))
    return redirect


# --------------------------------------------------------------------------
# Comments
# --------------------------------------------------------------------------

@router.get("/api/submissions/{submission_id}/comments", response_model=list[CommentPublic])
def list_comments(
    submission_id: int,
    session: Session = Depends(get_session),
) -> list[CommentPublic]:
    """Public: comments are discussion, not score data, so they are readable
    during the hidden window."""
    _votable_submission(session, submission_id)
    rows = session.exec(
        select(Comment).where(Comment.submission_id == submission_id).order_by(Comment.id)
    ).all()
    out: list[CommentPublic] = []
    for comment in rows:
        author = session.get(User, comment.user_id)
        out.append(
            CommentPublic(
                id=comment.id,
                submission_id=comment.submission_id,
                author_name=author.name if author else "Former participant",
                body=comment.body,
                created_at=comment.created_at,
            )
        )
    return out


@router.post("/api/submissions/{submission_id}/comments", response_model=CommentPublic, status_code=status.HTTP_201_CREATED)
def add_comment(
    submission_id: int,
    payload: CommentWrite,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> CommentPublic:
    _votable_submission(session, submission_id)
    _rate_limit(comment_limiter, f"comment:{user.id}", "commenting")

    comment = Comment(
        event_id=session.get(Submission, submission_id).event_id,
        submission_id=submission_id,
        user_id=user.id,
        body=payload.body,
    )
    session.add(comment)
    record(session, "comment.added", actor=user, entity_type="submission", entity_id=submission_id)
    session.commit()
    session.refresh(comment)
    return CommentPublic(
        id=comment.id,
        submission_id=comment.submission_id,
        author_name=user.name,
        body=comment.body,
        created_at=comment.created_at,
    )


@router.delete("/api/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    """Your own comment, or any comment if you are moderating the event."""
    comment = session.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found.")
    if comment.user_id != user.id and user.role not in (Role.organizer, Role.admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own comments.")
    session.delete(comment)
    record(session, "comment.deleted", actor=user, entity_type="comment", entity_id=comment_id)
    session.commit()


# --------------------------------------------------------------------------
# Public results -- withheld in the response during the hidden window
# --------------------------------------------------------------------------

@router.get("/api/events/{event_id}/public-results", response_model=list[PublicResultRow])
def public_results(
    event_id: int,
    background_tasks: BackgroundTasks,
    user: "User | None" = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> list[PublicResultRow]:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    if not may_see_results(event, user):
        # 425 Too Early says exactly what is happening: not forbidden forever,
        # just not yet. The message names the moment so the UI can explain it.
        raise HTTPException(
            status.HTTP_425_TOO_EARLY,
            f"Results are hidden until voting closes on "
            f"{event.results_hidden_until.strftime('%d %b %Y at %H:%M UTC')}.",
        )
    # event.results_revealed fires once, on the first real read after the
    # reveal moment has actually passed -- checked lazily here, not via a
    # scheduler. results_are_public() (not may_see_results()) is the right
    # check: an organizer reading early must not fire this prematurely.
    if (
        not event.results_revealed_notified
        and event.results_hidden_until is not None
        and results_are_public(event)
    ):
        event.results_revealed_notified = True
        session.add(event)
        session.commit()
        notify(session, background_tasks, event_id, "event.results_revealed")

    submissions = session.exec(
        select(Submission).where(
            Submission.event_id == event_id, Submission.status == SubmissionStatus.submitted
        )
    ).all()
    counts = {s.id: _count_votes(session, s.id) for s in submissions}
    ordered = sorted(submissions, key=lambda s: (-counts[s.id], s.id))
    rows: list[PublicResultRow] = []
    for rank, submission in enumerate(ordered, start=1):
        team = session.get(Team, submission.team_id)
        rows.append(
            PublicResultRow(
                rank=rank,
                submission_id=submission.id,
                submission_title=submission.title or "Untitled submission",
                team_name=team.name if team else "",
                votes=counts[submission.id],
            )
        )
    return rows
