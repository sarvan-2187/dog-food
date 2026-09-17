from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..auth import Role, User, require_role
from ..db import get_session
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
    session.commit()
    session.refresh(event)
    return event


@router.get("", response_model=list[Event])
def list_events(session: Session = Depends(get_session)) -> list[Event]:
    return list(session.exec(select(Event).order_by(Event.start_at)))


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
    _: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> Event:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, key, value)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: int,
    _: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> None:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    session.delete(event)
    session.commit()
