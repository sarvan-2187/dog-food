"""Votes and comments (PLAN.md Phase 3)."""
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, get_current_user, get_current_user_optional
from ..db import get_session
from ..events.models import Event
from ..events.visibility import may_see_results, results_are_public
from ..submissions.models import Submission, SubmissionStatus
from ..teams.models import Team
from .models import Comment, Vote
from .ratelimit import comment_limiter, vote_limiter
from .schemas import CommentPublic, CommentWrite, PublicResultRow, VoteResult

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
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> VoteResult:
    submission, event = _votable_submission(session, submission_id)
    if not event.voting_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Community voting is not open for this event.")
    _rate_limit(vote_limiter, f"vote:{user.id}", "voting")

    fingerprint = _client_fingerprint(request)
    vote = Vote(
        event_id=event.id,
        submission_id=submission_id,
        user_id=user.id,
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

    # Soft signal: several accounts voting from one client. Flagged for an
    # organizer, never used to block (PLAN.md Phase 3).
    others = session.exec(
        select(Vote).where(
            Vote.event_id == event.id,
            Vote.fingerprint_hash == fingerprint,
            Vote.user_id != user.id,
        )
    ).all()
    distinct_users = {v.user_id for v in others}
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

    record(session, "vote.cast", actor=user, entity_type="submission", entity_id=submission_id)
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
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> VoteResult:
    submission, event = _votable_submission(session, submission_id)
    if not event.voting_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Community voting is not open for this event.")
    vote = session.exec(
        select(Vote).where(Vote.submission_id == submission_id, Vote.user_id == user.id)
    ).first()
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
