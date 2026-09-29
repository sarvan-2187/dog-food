"""An event's judge pool and its progress (PLAN.md Phase 10.1, 10.3, 10.7).

Judges belong to events: assignment draws only from `event_judges`, so these
endpoints are how an organizer shapes that pool - add an existing judge, see who
has scored what, remove someone who dropped out, nudge someone who is behind -
and how a judge steps back from a submission they have a conflict with.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import func
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, require_role
from ..auth import mailer
from ..db import get_session
from ..events.models import Event
from ..scoring.models import Score
from ..submissions.models import Submission
from ..timeutil import utcnow
from ..ratelimit import judge_reminder_limiter
from .assignment import outside_track
from .models import EventJudge, JudgeAssignment, JudgeConflict

router = APIRouter(tags=["event-judges"])

ORGANIZER = (Role.organizer, Role.admin)


def judge_track(session: Session, event_id: int, judge_id: int) -> Optional[str]:
    """This judge's track on this event, or None when they take any track."""
    member = session.exec(
        select(EventJudge).where(EventJudge.event_id == event_id, EventJudge.user_id == judge_id)
    ).first()
    return member.track if member else None


def assignment_outside_track(session: Session, assignment: JudgeAssignment) -> bool:
    submission = session.get(Submission, assignment.submission_id)
    return outside_track(
        judge_track(session, assignment.event_id, assignment.judge_id), submission.track if submission else ""
    )


def assert_in_track(session: Session, assignment: JudgeAssignment) -> None:
    """DOGFOOD T2: a track judge must never see another track. Checked on every
    judge read or write of an assignment, not only when assigning, so a row left
    over from before the judge got a track (or written by hand) still can't be
    used to read or score an entry outside it."""
    if assignment_outside_track(session, assignment):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This submission is outside the track you are judging.")


def _event_or_404(session: Session, event_id: int) -> Event:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    return event


class ConflictPublic(BaseModel):
    submission_id: int
    submission_title: str
    reason: str
    created_at: datetime


class EventJudgePublic(BaseModel):
    user_id: int
    name: str
    email: str
    track: Optional[str] = None
    assigned: int
    scored: int
    last_activity: Optional[datetime]
    conflicts: list[ConflictPublic]


class EventJudges(BaseModel):
    """Leads with the one number an organizer checks first (PLAN.md 4.4)."""

    scored: int
    assigned: int
    judges: list[EventJudgePublic]
    email_enabled: bool
    judging_deadline: Optional[datetime] = None


@router.get("/api/events/{event_id}/judges", response_model=EventJudges)
def list_event_judges(
    event_id: int,
    _: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> EventJudges:
    event = _event_or_404(session, event_id)
    members = list(session.exec(select(EventJudge).where(EventJudge.event_id == event_id)))
    assignments = list(session.exec(select(JudgeAssignment).where(JudgeAssignment.event_id == event_id)))
    assignment_ids = [a.id for a in assignments]
    scores = (
        {s.assignment_id: s for s in session.exec(select(Score).where(Score.assignment_id.in_(assignment_ids)))}
        if assignment_ids
        else {}
    )
    conflicts = list(session.exec(select(JudgeConflict).where(JudgeConflict.event_id == event_id)))
    titles = {
        s.id: s.title or "Untitled submission"
        for s in session.exec(select(Submission).where(Submission.event_id == event_id))
    }

    rows: list[EventJudgePublic] = []
    for member in members:
        user = session.get(User, member.user_id)
        if user is None:
            continue
        mine = [a for a in assignments if a.judge_id == user.id]
        my_scores = [scores[a.id] for a in mine if a.id in scores]
        rows.append(
            EventJudgePublic(
                user_id=user.id,
                name=user.name,
                email=user.email,
                track=member.track,
                assigned=len(mine),
                scored=len(my_scores),
                last_activity=max((s.updated_at for s in my_scores), default=None),
                conflicts=[
                    ConflictPublic(
                        submission_id=c.submission_id,
                        submission_title=titles.get(c.submission_id, ""),
                        reason=c.reason,
                        created_at=c.created_at,
                    )
                    for c in conflicts
                    if c.judge_id == user.id
                ],
            )
        )
    # Furthest behind first: that's who the organizer needs to act on.
    rows.sort(key=lambda r: (r.scored - r.assigned, r.name.lower()))
    return EventJudges(
        scored=len(scores),
        assigned=len(assignments),
        judges=rows,
        email_enabled=mailer.CONFIG.enabled,
        judging_deadline=event.judging_deadline,
    )


class AddJudge(BaseModel):
    email: EmailStr


@router.post("/api/events/{event_id}/judges", response_model=EventJudgePublic, status_code=status.HTTP_201_CREATED)
def add_existing_judge(
    event_id: int,
    payload: AddJudge,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> EventJudgePublic:
    """For a judge who already has an account - no need to send them a fresh
    invitation for every event they work on."""
    _event_or_404(session, event_id)
    judge = session.exec(select(User).where(User.email == payload.email)).first()
    if judge is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No HackFlow account uses that email address - send them an invitation instead."
        )
    if judge.role != Role.judge:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"That account is a {judge.role.value}, not a judge - send them a judge invitation instead.",
        )
    existing = session.exec(
        select(EventJudge).where(EventJudge.event_id == event_id, EventJudge.user_id == judge.id)
    ).first()
    if existing is None:
        session.add(EventJudge(event_id=event_id, user_id=judge.id, added_by_id=user.id))
        record(session, "event_judge.added", actor=user, entity_type="event", entity_id=event_id, judge_id=judge.id)
        session.commit()
    return EventJudgePublic(
        user_id=judge.id,
        name=judge.name,
        email=judge.email,
        track=existing.track if existing else None,
        assigned=0,
        scored=0,
        last_activity=None,
        conflicts=[],
    )


class JudgeTrack(BaseModel):
    # None (or "") means the judge takes any track.
    track: Optional[str] = None


@router.put("/api/events/{event_id}/judges/{user_id}/track", response_model=JudgeTrack)
def set_judge_track(
    event_id: int,
    user_id: int,
    payload: JudgeTrack,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> JudgeTrack:
    """Give a judge on this event's panel one track, or clear it. Takes effect on
    reads at once (assert_in_track); unscored assignments outside the new track
    are released the next time assignment runs, and scores already given stand."""
    event = _event_or_404(session, event_id)
    member = session.exec(
        select(EventJudge).where(EventJudge.event_id == event_id, EventJudge.user_id == user_id)
    ).first()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That person isn't judging this event.")
    track = (payload.track or "").strip() or None
    if track is not None and track not in (event.tracks or []):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"This event has no track called {track!r}."
        )
    if member.track != track:
        member.track = track
        session.add(member)
        record(
            session, "event_judge.track_set", actor=user, entity_type="event", entity_id=event_id,
            judge_id=user_id, track=track,
        )
        session.commit()
    return JudgeTrack(track=track)


class RemovalResult(BaseModel):
    removed_assignments: int
    kept_scores: int


@router.delete("/api/events/{event_id}/judges/{user_id}", response_model=RemovalResult)
def remove_event_judge(
    event_id: int,
    user_id: int,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> RemovalResult:
    """For a judge who dropped out. Their unscored work is released for
    re-assignment; any score they already submitted stands - it was a real
    judgement made while they were on the panel."""
    _event_or_404(session, event_id)
    member = session.exec(
        select(EventJudge).where(EventJudge.event_id == event_id, EventJudge.user_id == user_id)
    ).first()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That person isn't judging this event.")
    assignments = list(
        session.exec(
            select(JudgeAssignment).where(JudgeAssignment.event_id == event_id, JudgeAssignment.judge_id == user_id)
        )
    )
    scored_ids = (
        {
            s.assignment_id
            for s in session.exec(select(Score).where(Score.assignment_id.in_([a.id for a in assignments])))
        }
        if assignments
        else set()
    )
    removed = 0
    for assignment in assignments:
        if assignment.id not in scored_ids:
            session.delete(assignment)
            removed += 1
    session.delete(member)
    record(
        session,
        "event_judge.removed",
        actor=user,
        entity_type="event",
        entity_id=event_id,
        judge_id=user_id,
        removed_assignments=removed,
        kept_scores=len(scored_ids),
    )
    session.commit()
    return RemovalResult(removed_assignments=removed, kept_scores=len(scored_ids))


class ReminderResult(BaseModel):
    sent_to: str
    remaining: int


@router.post("/api/events/{event_id}/judges/{user_id}/remind", response_model=ReminderResult)
def remind_judge(
    event_id: int,
    user_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> ReminderResult:
    """Opt-in email, like every other Phase 9/10 email: with email off this
    refuses and opens no connection."""
    event = _event_or_404(session, event_id)
    if not mailer.CONFIG.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email isn't set up here, so reminders can't be sent.")
    judge = session.get(User, user_id)
    in_pool = session.exec(
        select(EventJudge).where(EventJudge.event_id == event_id, EventJudge.user_id == user_id)
    ).first()
    if judge is None or in_pool is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That person isn't judging this event.")
    assignment_ids = [
        a.id
        for a in session.exec(
            select(JudgeAssignment).where(JudgeAssignment.event_id == event_id, JudgeAssignment.judge_id == user_id)
        )
    ]
    scored = (
        session.exec(select(func.count()).select_from(Score).where(Score.assignment_id.in_(assignment_ids))).one()
        if assignment_ids
        else 0
    )
    remaining = len(assignment_ids) - scored
    if remaining <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{judge.name} has already scored everything assigned to them.")
    allowed, retry_after = judge_reminder_limiter.check(f"remind:{event_id}:{user_id}")
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"{judge.name} was reminded recently - you can send another in about "
            f"{max(1, round(retry_after / 60))} minutes.",
        )
    first = judge.name.split()[0] if judge.name.strip() else "there"
    plural = "" if remaining == 1 else "s"
    due = f" Scores are due by {event.judging_deadline:%d %b %Y, %H:%M} UTC." if event.judging_deadline else ""
    text = (
        f"Hi {first},\n\n"
        f"A reminder from the organizers of {event.name}: you have {remaining} project{plural} "
        f"still to score.{due}\n\n{mailer.APP_BASE_URL}/judge\n\nThank you for judging.\n\n- HackFlow\n"
    )
    background_tasks.add_task(
        mailer.send_quietly, judge.email, f"{remaining} project{plural} left to score - {event.name}", text
    )
    record(session, "event_judge.reminded", actor=user, entity_type="event", entity_id=event_id, judge_id=user_id)
    session.commit()
    return ReminderResult(sent_to=judge.email, remaining=remaining)


class ConflictDeclaration(BaseModel):
    reason: str = ""

    @field_validator("reason")
    @classmethod
    def reason_len(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 300:
            raise ValueError("Keep the reason to 300 characters or fewer.")
        return v


@router.post("/api/assignments/{assignment_id}/conflict", status_code=status.HTTP_204_NO_CONTENT)
def declare_conflict(
    assignment_id: int,
    payload: ConflictDeclaration,
    user: User = Depends(require_role(Role.judge)),
    session: Session = Depends(get_session),
) -> None:
    """A judge steps back from one submission. The assignment is released and a
    permanent conflict recorded, so assignment never hands it back to them."""
    assignment = session.get(JudgeAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found.")
    if assignment.judge_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This submission is assigned to a different judge.")
    if session.exec(select(Score).where(Score.assignment_id == assignment_id)).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You've already scored this project. Ask the organizer to remove your score if you have a conflict.",
        )
    session.add(
        JudgeConflict(
            event_id=assignment.event_id,
            judge_id=user.id,
            submission_id=assignment.submission_id,
            reason=payload.reason,
        )
    )
    session.delete(assignment)
    record(
        session,
        "judge.conflict_declared",
        actor=user,
        entity_type="submission",
        entity_id=assignment.submission_id,
        reason=payload.reason,
    )
    session.commit()


class JudgeEvent(BaseModel):
    event_id: int
    name: str
    slug: str
    end_at: datetime
    judging_open: bool
    judging_deadline: Optional[datetime] = None


@router.get("/api/judge/events", response_model=list[JudgeEvent])
def my_judging_events(
    user: User = Depends(require_role(Role.judge)),
    session: Session = Depends(get_session),
) -> list[JudgeEvent]:
    """The events a judge is on, so their dashboard can say "Judging for X opens
    on ..." instead of showing an empty list before the deadline (PLAN.md 10.3)."""
    now = utcnow()
    events = session.exec(
        select(Event).join(EventJudge, EventJudge.event_id == Event.id).where(EventJudge.user_id == user.id)
    ).all()
    return [
        JudgeEvent(event_id=e.id, name=e.name, slug=e.slug, end_at=e.end_at, judging_open=now >= e.end_at,
                   judging_deadline=e.judging_deadline)
        for e in sorted(events, key=lambda e: e.end_at)
    ]
