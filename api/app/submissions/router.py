from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlmodel import Session, select

from ..db import get_session
from ..events.models import Event
from ..teams.deps import require_team_member
from ..teams.models import Team
from ..timeutil import utcnow
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
    session: Session = Depends(get_session),
) -> Submission:
    _load_open_event(session, team.event_id)
    sub = session.exec(select(Submission).where(Submission.team_id == team_id)).first()
    if not sub or not sub.title.strip() or not sub.description.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add a title and description before submitting.")
    sub.status = SubmissionStatus.submitted
    sub.updated_at = utcnow()
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub


@router.get("/api/gallery", response_model=list[Submission])
def gallery(
    event_id: "int | None" = None,
    q: "str | None" = Query(default=None),
    session: Session = Depends(get_session),
) -> list[Submission]:
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
    stmt = stmt.order_by(Submission.updated_at.desc())
    return list(session.exec(stmt))
