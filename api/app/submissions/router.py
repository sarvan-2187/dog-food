import random
from collections import Counter

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, get_current_user, get_current_user_optional, require_role
from ..judging.models import JudgeAssignment
from ..scoring.models import Score
from ..db import get_session
from ..events.models import Event
from ..events.visibility import may_see_results
from ..storage.lookup import image_url_for, image_urls_for
from ..teams.deps import require_team_member
from ..teams.models import Team, TeamMembership
from ..timeutil import utcnow
from ..voting.models import Comment, Vote
from ..voting.schemas import GalleryItem
from ..voting.voter import read_voter_key
from ..webhooks.service import notify
from .models import Submission, SubmissionStatus, in_competition
from ..scoring.awards import awards_by_submission
from .schemas import EligibilityRow, EligibilityUpdate, SubmissionPublic, SubmissionUpdate

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


def _public(session: Session, sub: Submission) -> SubmissionPublic:
    return SubmissionPublic(
        id=sub.id,
        team_id=sub.team_id,
        event_id=sub.event_id,
        title=sub.title,
        description=sub.description,
        track=sub.track,
        status=sub.status.value,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
        image_url=image_url_for(session, "submission", sub.id),
        repo_url=sub.repo_url,
        demo_url=sub.demo_url,
        video_url=sub.video_url,
        disqualified_at=sub.disqualified_at,
        disqualified_reason=sub.disqualified_reason,
    )


@router.get("/api/events/{event_id}/eligibility", response_model=list[EligibilityRow])
def list_eligibility(
    event_id: int,
    _: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> list[EligibilityRow]:
    """Every submitted entry with automatic eligibility flags, disqualified ones
    first and flagged ones next, so the organizer can rule on each and undo a
    ruling from the same list. Flags only inform: nothing is disqualified
    automatically, because every check here has legitimate exceptions."""
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    subs = session.exec(
        select(Submission).where(Submission.event_id == event_id, Submission.status == SubmissionStatus.submitted)
    ).all()
    teams = {t.id: t.name for t in session.exec(select(Team).where(Team.event_id == event_id))}
    members = Counter(
        m.team_id for m in session.exec(select(TeamMembership).where(TeamMembership.team_id.in_(list(teams) or [0])))
    )
    repos = Counter(_repo_key(s.repo_url) for s in subs if s.repo_url.strip())
    rows = [
        EligibilityRow(
            submission_id=s.id,
            title=s.title or "Untitled submission",
            team_name=teams.get(s.team_id, ""),
            disqualified_at=s.disqualified_at,
            disqualified_reason=s.disqualified_reason,
            flags=eligibility_flags(s, event, members[s.team_id], repos),
        )
        for s in subs
    ]
    return sorted(rows, key=lambda r: (r.disqualified_at is None, not r.flags, r.title.lower(), r.submission_id))


MIN_DESCRIPTION = 40


def _repo_key(url: str) -> str:
    return url.strip().lower().rstrip("/").removesuffix(".git")


def eligibility_flags(sub: Submission, event: Event, member_count: int, repos: Counter) -> list[str]:
    """Plain-language reasons an organizer may want to look twice at an entry."""
    flags = []
    if not sub.repo_url.strip():
        flags.append("No code repository link.")
    elif repos[_repo_key(sub.repo_url)] > 1:
        flags.append("Same repository as another entry in this event.")
    if len((sub.description or "").strip()) < MIN_DESCRIPTION:
        flags.append(f"Description is under {MIN_DESCRIPTION} characters.")
    if event.tracks and not sub.track:
        flags.append("No track chosen.")
    if member_count > event.max_team_size:
        flags.append(f"Team has {member_count} members; the limit is {event.max_team_size}.")
    return flags


@router.post("/api/submissions/{submission_id}/eligibility", response_model=SubmissionPublic)
def set_eligibility(
    submission_id: int,
    payload: EligibilityUpdate,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> SubmissionPublic:
    """Disqualify or reinstate. A disqualified entry leaves the gallery, voting,
    assignment, awards and standings; its scores stay, so reinstating restores it."""
    sub = session.get(Submission, submission_id)
    if not sub or sub.status != SubmissionStatus.submitted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Only a submitted project can be ruled on.")
    reason = payload.reason.strip()
    if payload.eligible:
        sub.disqualified_at, sub.disqualified_reason = None, ""
        action = "submission.reinstated"
    else:
        if not reason:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give a reason - the team will see it.")
        sub.disqualified_at, sub.disqualified_reason = utcnow(), reason[:500]
        action = "submission.disqualified"
        # Unscored work would sit on judges' lists for nothing. Scored assignments
        # stay with their scores.
        scored = select(Score.assignment_id).where(Score.submission_id == sub.id)
        for assignment in session.exec(
            select(JudgeAssignment).where(
                JudgeAssignment.submission_id == sub.id, JudgeAssignment.id.not_in(scored)
            )
        ):
            session.delete(assignment)
    session.add(sub)
    record(session, action, actor=user, entity_type="submission", entity_id=sub.id, reason=reason)
    session.commit()
    session.refresh(sub)
    notify(session, background_tasks, sub.event_id, action, submission_id=sub.id, title=sub.title)
    return _public(session, sub)


@router.get("/api/teams/{team_id}/submission", response_model=SubmissionPublic)
def get_submission(
    team_id: int,
    team: Team = Depends(require_team_member),
    session: Session = Depends(get_session),
) -> SubmissionPublic:
    sub = session.exec(select(Submission).where(Submission.team_id == team_id)).first()
    if not sub:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No submission started yet.")
    return _public(session, sub)


@router.patch("/api/teams/{team_id}/submission", response_model=SubmissionPublic)
def upsert_submission(
    team_id: int,
    payload: SubmissionUpdate,
    team: Team = Depends(require_team_member),
    session: Session = Depends(get_session),
) -> SubmissionPublic:
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
    return _public(session, sub)


@router.post("/api/teams/{team_id}/submission/submit", response_model=SubmissionPublic)
def submit_submission(
    team_id: int,
    background_tasks: BackgroundTasks,
    team: Team = Depends(require_team_member),
    _member: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SubmissionPublic:
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
    notify(session, background_tasks, sub.event_id, "submission.submitted", submission_id=sub.id, title=sub.title)
    return _public(session, sub)


@router.get("/api/gallery", response_model=list[GalleryItem])
def gallery(
    request: Request,
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
    stmt = select(Submission).where(in_competition())
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
    # PLAN.md 10.12: nothing from a draft event is public.
    stmt = stmt.join(Event, Event.id == Submission.event_id).where(Event.status == "published")
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
    guest_key = None if user else read_voter_key(request)
    for vote in vote_rows:
        votes[vote.submission_id] = votes.get(vote.submission_id, 0) + 1
        if (user is not None and vote.user_id == user.id) or (guest_key and vote.voter_key == guest_key):
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

    images = image_urls_for(session, "submission", [r.id for r in rows])
    won = awards_by_submission(session, [r.id for r in rows if visible.get(r.event_id, False)])
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
            image_url=images.get(r.id),
            repo_url=r.repo_url,
            demo_url=r.demo_url,
            video_url=r.video_url,
            awards=won.get(r.id, []),
        )
        for r in rows
    ]


@router.get("/api/submissions/{submission_id}", response_model=GalleryItem)
def get_public_submission(
    submission_id: int,
    request: Request,
    user: "User | None" = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> GalleryItem:
    """Public detail for one gallery entry. Carries no score data at any time."""
    submission = session.get(Submission, submission_id)
    if not submission or not submission.competing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That submission is not in the public gallery.")
    event = session.get(Event, submission.event_id)
    if event is not None and event.status != "published":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That submission is not in the public gallery.")
    visible = may_see_results(event, user) if event else False

    vote_rows = session.exec(select(Vote).where(Vote.submission_id == submission_id)).all()
    guest_key = None if user else read_voter_key(request)
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
        voted_by_me=any(
            (user is not None and v.user_id == user.id) or (guest_key and v.voter_key == guest_key)
            for v in vote_rows
        ),
        image_url=image_url_for(session, "submission", submission.id),
        repo_url=submission.repo_url,
        demo_url=submission.demo_url,
        video_url=submission.video_url,
        awards=awards_by_submission(session, [submission.id]).get(submission.id, []) if visible else [],
    )
