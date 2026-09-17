from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, require_role
from ..db import get_session
from ..submissions.models import Submission
from ..teams.models import Team
from .models import Event
from .schemas import EventCreate, EventUpdate

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("", response_model=Event, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: EventCreate,
    user: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> Event:
    if session.exec(select(Event).where(Event.slug == payload.slug)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An event with this slug already exists.")
    event = Event(**payload.model_dump(), created_by_id=user.id)
    session.add(event)
    session.flush()
    record(session, "event.created", actor=user, entity_type="event", entity_id=event.id, slug=event.slug)
    session.commit()
    session.refresh(event)
    return event


@router.get("", response_model=list[Event])
def list_events(session: Session = Depends(get_session)) -> list[Event]:
    return list(session.exec(select(Event).order_by(Event.start_at)))


@router.get("/id/{event_id}", response_model=Event)
def get_event_by_id(event_id: int, session: Session = Depends(get_session)) -> Event:
    """By id, for screens that hold an event_id rather than a slug -- the
    submission page needs the deadline and only knows its team's event_id.
    Declared before /{slug} so the literal segment wins."""
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    return event


@router.get("/{slug}", response_model=Event)
def get_event(slug: str, session: Session = Depends(get_session)) -> Event:
    event = session.exec(select(Event).where(Event.slug == slug)).first()
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    return event


@router.patch("/{event_id}", response_model=Event)
def update_event(
    event_id: int,
    payload: EventUpdate,
    user: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> Event:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    start = changes.get("start_at", event.start_at)
    end = changes.get("end_at", event.end_at)
    if end <= start:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "End date must be after the start date.",
        )
    for key, value in changes.items():
        setattr(event, key, value)
    session.add(event)
    record(
        session,
        "event.updated",
        actor=user,
        entity_type="event",
        entity_id=event.id,
        changed=sorted(changes),
    )
    session.commit()
    session.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: int,
    user: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> None:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    # Deleting an event with dependents is a foreign-key violation in Postgres,
    # which would surface as a bare 500. Refuse it with a message that names the
    # consequence in plain language instead (PLAN.md 4.3, 4.6).
    teams = len(session.exec(select(Team).where(Team.event_id == event_id)).all())
    submissions = len(session.exec(select(Submission).where(Submission.event_id == event_id)).all())
    if teams or submissions:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This event has {teams} team(s) and {submissions} submission(s). "
            "Deleting it would destroy their work, so it cannot be deleted while they exist.",
        )
    record(session, "event.deleted", actor=user, entity_type="event", entity_id=event_id, slug=event.slug)
    session.delete(event)
    session.commit()
