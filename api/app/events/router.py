from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, get_current_user_optional, require_role
from ..db import get_session
from ..submissions.models import Submission
from ..teams.models import Team
from ..judging.models import Rubric
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
    # PLAN.md 10.12: new events start as drafts, visible only to organizers
    # until they're published.
    event = Event(**payload.model_dump(), created_by_id=user.id, status="draft")
    session.add(event)
    session.flush()
    record(session, "event.created", actor=user, entity_type="event", entity_id=event.id, slug=event.slug)
    session.commit()
    session.refresh(event)
    return event


def _can_see_drafts(user: "User | None") -> bool:
    return user is not None and user.role in (Role.organizer, Role.admin)


def visible_or_404(event: "Event | None", user: "User | None") -> Event:
    """A draft is 404, not 403, to everyone but organizers, so its existence
    doesn't leak (PLAN.md 10.12)."""
    if event is None or (event.status != "published" and not _can_see_drafts(user)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    return event


@router.get("", response_model=list[Event])
def list_events(
    user: "User | None" = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> list[Event]:
    stmt = select(Event).order_by(Event.start_at)
    if not _can_see_drafts(user):
        stmt = stmt.where(Event.status == "published")
    return list(session.exec(stmt))


@router.get("/id/{event_id}", response_model=Event)
def get_event_by_id(
    event_id: int,
    user: "User | None" = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> Event:
    """By id, for screens that hold an event_id rather than a slug -- the
    submission page needs the deadline and only knows its team's event_id.
    Declared before /{slug} so the literal segment wins."""
    return visible_or_404(session.get(Event, event_id), user)


@router.get("/{slug}", response_model=Event)
def get_event(
    slug: str,
    user: "User | None" = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> Event:
    return visible_or_404(session.exec(select(Event).where(Event.slug == slug)).first(), user)


class CriterionPublic(BaseModel):
    rubric: str
    label: str
    weight: float
    max_score: float
    description: str = ""


@router.get("/{event_id}/criteria", response_model=list[CriterionPublic])
def public_criteria(
    event_id: int,
    user: "User | None" = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> list[CriterionPublic]:
    """What projects are judged on - names, weights and descriptions, never a
    score (PLAN.md 10.8). Public, because entrants should know the rules."""
    visible_or_404(session.get(Event, event_id), user)
    return [
        CriterionPublic(
            rubric=rubric.name,
            label=c["label"],
            weight=c["weight"],
            max_score=c.get("max_score", 10),
            description=c.get("description", ""),
        )
        for rubric in session.exec(select(Rubric).where(Rubric.event_id == event_id).order_by(Rubric.id))
        for c in rubric.criteria
    ]


@router.post("/{event_id}/publish", response_model=Event)
def publish_event(
    event_id: int,
    user: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> Event:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    event.status = "published"
    session.add(event)
    record(session, "event.published", actor=user, entity_type="event", entity_id=event.id)
    session.commit()
    session.refresh(event)
    return event


@router.post("/{event_id}/unpublish", response_model=Event)
def unpublish_event(
    event_id: int,
    user: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> Event:
    """Only while nobody has joined: hiding an event with teams would strand them."""
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    teams = len(session.exec(select(Team).where(Team.event_id == event_id)).all())
    if teams:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{teams} team(s) have already joined, so this event can't go back to being a draft.",
        )
    event.status = "draft"
    session.add(event)
    record(session, "event.unpublished", actor=user, entity_type="event", entity_id=event.id)
    session.commit()
    session.refresh(event)
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
