import random

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import User, get_current_user, get_current_user_optional
from ..db import get_session
from ..events.models import Event
from ..events.visibility import may_see_results
from ..teams.deps import require_team_member
from ..teams.models import Team
from ..timeutil import utcnow
from ..voting.models import Comment, Vote
from ..voting.schemas import GalleryItem
from .models import Submission, SubmissionStatus
from .schemas import SubmissionUpdate

router = APIRouter(tags=["submissions"])


def _load_open_event(session: Session, event_id: int) -> Event:
    """Resolve the event and enforce its deadline server-side (PLAN.md Phase 1)."""
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This event no longer exists.")
    if utcnow() > event.end_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The submission deadline for this event has passed.")
    return event


def _escape_like(term: str) -> str:
    """Neutralise ILIKE wildcards so a literal % or _ in a search box matches
    itself instead of everything."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/api/teams/{team_id}/submission", response_model=Submission)
def get_submission(
    team_id: int,
    team: Team = Depends(require_team_member),
    session: Session = Depends(get_session),
) -> Submission:
    sub = session.exec(select(Submission).where(Submission.team_id == team_id)).first()
    if not sub:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No submission started yet.")
    return sub


@router.patch("/api/teams/{team_id}/submission", response_model=Submission)
def upsert_submission(
    team_id: int,
    payload: SubmissionUpdate,
    team: Team = Depends(require_team_member),
    session: Session = Depends(get_session),
) -> Submission:
    _load_open_event(session, team.event_id)
    sub = session.exec(select(Submission).where(Submission.team_id == team_id)).first()
    if not sub:
        sub = Submission(team_id=team_id, event_id=team.event_id)
    # exclude_none as well as exclude_unset: {"title": null} means "no change",
    # never "write NULL" into a non-nullable column.
    for key, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(sub, key, value)
    sub.updated_at = utcnow()
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub


@router.post("/api/teams/{team_id}/submission/submit", response_model=Submission)
def submit_submission(
    team_id: int,
    team: Team = Depends(require_team_member),
    _member: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Submission:
    _load_open_event(session, team.event_id)
    sub = session.exec(select(Submission).where(Submission.team_id == team_id)).first()
    if not sub or not sub.title.strip() or not sub.description.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add a title and description before submitting.")
    sub.status = SubmissionStatus.submitted
    sub.updated_at = utcnow()
    session.add(sub)
    record(session, "submission.submitted", actor=_member, entity_type="submission", entity_id=sub.id)
    session.commit()
    session.refresh(sub)
    return sub


@router.get("/api/gallery", response_model=list[GalleryItem])
def gallery(
    event_id: "int | None" = None,
    q: "str | None" = Query(default=None),
    order: str = Query(default="recent", pattern="^(recent|random|votes)$"),
    seed: "int | None" = Query(
        default=None,
        description="Stable shuffle seed. The client keeps one per browser session so "
        "repeated visits see the same order instead of the page reshuffling under them.",
    ),
    user: "User | None" = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> list[GalleryItem]:
    stmt = select(Submission).where(Submission.status == SubmissionStatus.submitted)
    if event_id is not None:
        stmt = stmt.where(Submission.event_id == event_id)
    if q:
        like = f"%{_escape_like(q)}%"
        stmt = stmt.where(
            or_(
                Submission.title.ilike(like, escape="\\"),
                Submission.description.ilike(like, escape="\\"),
            )
        )
    rows = list(session.exec(stmt.order_by(Submission.updated_at.desc())))
    if not rows:
        return []

    # Vote counts are withheld from the *response* during the hidden window, not
    # merely hidden by the UI (PLAN.md Phase 3). Resolved per event, since a
    # cross-event gallery can span both states.
    events = {e.id: e for e in session.exec(select(Event).where(Event.id.in_({r.event_id for r in rows})))}
    visible = {eid: may_see_results(ev, user) for eid, ev in events.items()}

    vote_rows = session.exec(select(Vote).where(Vote.submission_id.in_([r.id for r in rows]))).all()
    votes: dict[int, int] = {}
    mine: set[int] = set()
    for vote in vote_rows:
        votes[vote.submission_id] = votes.get(vote.submission_id, 0) + 1
        if user is not None and vote.user_id == user.id:
            mine.add(vote.submission_id)

    comment_rows = session.exec(select(Comment).where(Comment.submission_id.in_([r.id for r in rows]))).all()
    comments: dict[int, int] = {}
    for comment in comment_rows:
        comments[comment.submission_id] = comments.get(comment.submission_id, 0) + 1

    if order == "random":
        # Seeded, so the same visitor sees the same order all session and the
        # grid does not jump around between visits (PLAN.md Phase 3 UX).
        random.Random(seed if seed is not None else 0).shuffle(rows)
    elif order == "votes":
        if not all(visible.get(r.event_id, False) for r in rows):
            raise HTTPException(
                status.HTTP_425_TOO_EARLY,
                "Submissions cannot be sorted by votes while results are hidden.",
            )
        rows.sort(key=lambda r: (-votes.get(r.id, 0), r.id))

    return [
        GalleryItem(
            id=r.id,
            event_id=r.event_id,
            team_id=r.team_id,
            title=r.title,
            description=r.description,
            track=r.track,
            updated_at=r.updated_at,
            comment_count=comments.get(r.id, 0),
            votes=votes.get(r.id, 0) if visible.get(r.event_id, False) else None,
            voted_by_me=r.id in mine,
        )
        for r in rows
    ]


@router.get("/api/submissions/{submission_id}", response_model=GalleryItem)
def get_public_submission(
    submission_id: int,
    user: "User | None" = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> GalleryItem:
    """Public detail for one gallery entry. Carries no score data at any time."""
    submission = session.get(Submission, submission_id)
    if not submission or submission.status != SubmissionStatus.submitted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That submission is not in the public gallery.")
    event = session.get(Event, submission.event_id)
    visible = may_see_results(event, user) if event else False

    vote_rows = session.exec(select(Vote).where(Vote.submission_id == submission_id)).all()
    comment_count = len(session.exec(select(Comment).where(Comment.submission_id == submission_id)).all())
    return GalleryItem(
        id=submission.id,
        event_id=submission.event_id,
        team_id=submission.team_id,
        title=submission.title,
        description=submission.description,
        track=submission.track,
        updated_at=submission.updated_at,
        comment_count=comment_count,
        votes=len(vote_rows) if visible else None,
        voted_by_me=any(user is not None and v.user_id == user.id for v in vote_rows),
    )
