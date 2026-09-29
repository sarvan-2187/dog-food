"""Event announcements (PLAN.md Phase 10.11).

Once an event was running, organizers had no way to tell participants anything
("the deadline moved", "demos start at 5"). Announcements are plain text -
never rendered as HTML - shown on the event page and on the dashboards of
everyone on a team in that event, optionally emailed (only when email is set
up), and posted to the event's webhooks so a Discord/Slack channel wired up in
Phase 7.3 gets them too.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, get_current_user, get_current_user_optional, require_role
from ..auth import mailer
from ..db import get_session
from ..teams.models import Team, TeamMembership
from ..timeutil import utcnow
from ..ratelimit import announcement_email_limiter
from ..webhooks.service import notify
from .models import Announcement, Event

router = APIRouter(tags=["announcements"])

ORGANIZER = (Role.organizer, Role.admin)


class AnnouncementEdit(BaseModel):
    title: str
    body: str

    @field_validator("title")
    @classmethod
    def title_len(cls, v: str) -> str:
        v = v.strip()
        if not (3 <= len(v) <= 120):
            raise ValueError("Title must be 3-120 characters.")
        return v

    @field_validator("body")
    @classmethod
    def body_len(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 2000):
            raise ValueError("Write the announcement - up to 2000 characters.")
        return v


class AnnouncementWrite(AnnouncementEdit):
    email_participants: bool = False


class AnnouncementPublic(BaseModel):
    id: int
    event_id: int
    event_name: str = ""
    event_slug: str = ""
    title: str
    body: str
    author_name: str
    emailed_count: int
    created_at: datetime
    updated_at: datetime
    email_queued: Optional[int] = None  # only on the create response


def _event_or_404(session: Session, event_id: int, user: "User | None") -> Event:
    from .router import visible_or_404  # router is imported by main after this module

    return visible_or_404(session.get(Event, event_id), user)


def _public(session: Session, a: Announcement, event: "Event | None" = None) -> AnnouncementPublic:
    author = session.get(User, a.author_id)
    event = event or session.get(Event, a.event_id)
    return AnnouncementPublic(
        id=a.id,
        event_id=a.event_id,
        event_name=event.name if event else "",
        event_slug=event.slug if event else "",
        title=a.title,
        body=a.body,
        author_name=author.name if author else "",
        emailed_count=a.emailed_count,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def _participant_emails(session: Session, event_id: int) -> list[str]:
    rows = session.exec(
        select(User.email)
        .join(TeamMembership, TeamMembership.user_id == User.id)
        .join(Team, Team.id == TeamMembership.team_id)
        .where(Team.event_id == event_id, User.is_active)
    ).all()
    return sorted(set(rows))


@router.get("/api/events/{event_id}/announcements", response_model=list[AnnouncementPublic])
def list_announcements(
    event_id: int,
    user: "User | None" = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> list[AnnouncementPublic]:
    event = _event_or_404(session, event_id, user)
    rows = session.exec(
        select(Announcement).where(Announcement.event_id == event_id).order_by(Announcement.created_at.desc())
    )
    return [_public(session, a, event) for a in rows]


@router.post(
    "/api/events/{event_id}/announcements", response_model=AnnouncementPublic, status_code=status.HTTP_201_CREATED
)
def post_announcement(
    event_id: int,
    payload: AnnouncementWrite,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> AnnouncementPublic:
    event = _event_or_404(session, event_id, user)
    recipients: list[str] = []
    if payload.email_participants:
        if not mailer.CONFIG.enabled:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Email isn't set up here, so this can only be posted on the site."
            )
        allowed, retry_after = announcement_email_limiter.check(f"announce:{event_id}")
        if not allowed:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "An announcement was emailed to this event in the last 10 minutes. Post this one without email, "
                f"or wait about {max(1, round(retry_after / 60))} minutes.",
            )
        recipients = _participant_emails(session, event_id)

    announcement = Announcement(
        event_id=event_id, author_id=user.id, title=payload.title, body=payload.body, emailed_count=len(recipients)
    )
    session.add(announcement)
    session.flush()
    record(
        session,
        "announcement.posted",
        actor=user,
        entity_type="event",
        entity_id=event_id,
        announcement_id=announcement.id,
        emailed=len(recipients),
    )
    session.commit()
    session.refresh(announcement)

    if recipients:
        link = f"{mailer.APP_BASE_URL}/events/{event.slug}"
        text = f"{payload.body}\n\n{link}\n\n- {user.name}, {event.name}\n"
        subject = f"{event.name}: {payload.title}"
        background_tasks.add_task(mailer.send_many_quietly, [(to, subject, text, None) for to in recipients])
    notify(
        session,
        background_tasks,
        event_id,
        "announcement.posted",
        announcement_id=announcement.id,
        title=announcement.title,
        body=announcement.body,
    )
    out = _public(session, announcement, event)
    out.email_queued = len(recipients)
    return out


def _own_announcement(session: Session, event_id: int, announcement_id: int) -> Announcement:
    a = session.get(Announcement, announcement_id)
    if a is None or a.event_id != event_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Announcement not found.")
    return a


@router.patch("/api/events/{event_id}/announcements/{announcement_id}", response_model=AnnouncementPublic)
def edit_announcement(
    event_id: int,
    announcement_id: int,
    payload: AnnouncementEdit,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> AnnouncementPublic:
    a = _own_announcement(session, event_id, announcement_id)
    a.title, a.body, a.updated_at = payload.title, payload.body, utcnow()
    session.add(a)
    record(session, "announcement.edited", actor=user, entity_type="event", entity_id=event_id, announcement_id=a.id)
    session.commit()
    session.refresh(a)
    return _public(session, a)


@router.delete("/api/events/{event_id}/announcements/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_announcement(
    event_id: int,
    announcement_id: int,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> None:
    a = _own_announcement(session, event_id, announcement_id)
    record(session, "announcement.deleted", actor=user, entity_type="event", entity_id=event_id, announcement_id=a.id)
    session.delete(a)
    session.commit()


@router.get("/api/announcements/mine", response_model=list[AnnouncementPublic])
def my_announcements(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[AnnouncementPublic]:
    """The latest announcements from every published event the user is on a
    team in, for their dashboard."""
    event_ids = session.exec(
        select(Team.event_id)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .where(TeamMembership.user_id == user.id)
    ).all()
    if not event_ids:
        return []
    rows = session.exec(
        select(Announcement)
        .join(Event, Event.id == Announcement.event_id)
        .where(Announcement.event_id.in_(set(event_ids)), Event.status == "published")
        .order_by(Announcement.created_at.desc())
        .limit(5)
    )
    return [_public(session, a) for a in rows]
