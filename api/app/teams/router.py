from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, get_current_user, require_role
from ..db import get_session
from ..events.models import Event
from ..timeutil import utcnow
from .deps import require_team_member
from .models import Team, TeamMembership
from .schemas import TeamCreate, TeamJoin, TeamMemberPublic, TeamPublic

router = APIRouter(tags=["teams"])


def _team_in_event(session: Session, user_id: int, event_id: int) -> Team | None:
    """The team this person is already on for this event, if any.

    Phase 10.2. One entrant, one team, per event. Membership rows carry only a
    team_id, so "already in this event" has to be resolved through the teams
    table rather than read off the membership directly. Enforced here on the
    server, because the consequence of getting it wrong is a person competing
    against themselves and, downstream, the conflict-of-interest rule in
    assignment silently protecting the wrong set of submissions.
    """
    memberships = session.exec(select(TeamMembership).where(TeamMembership.user_id == user_id)).all()
    if not memberships:
        return None
    return session.exec(
        select(Team).where(
            Team.id.in_([m.team_id for m in memberships]),
            Team.event_id == event_id,
        )
    ).first()


def _team_public(session: Session, team: Team) -> TeamPublic:
    memberships = session.exec(select(TeamMembership).where(TeamMembership.team_id == team.id)).all()
    members: list[TeamMemberPublic] = []
    for membership in memberships:
        member_user = session.get(User, membership.user_id)
        if member_user:
            members.append(TeamMemberPublic(id=member_user.id, name=member_user.name, email=member_user.email))
    event = session.get(Event, team.event_id)
    return TeamPublic(
        id=team.id,
        event_id=team.event_id,
        name=team.name,
        invite_code=team.invite_code,
        members=members,
        max_team_size=event.max_team_size if event else 4,
    )


@router.post("/api/events/{event_id}/teams", response_model=TeamPublic, status_code=status.HTTP_201_CREATED)
def create_team(
    event_id: int,
    payload: TeamCreate,
    user: User = Depends(require_role(Role.participant)),
    session: Session = Depends(get_session),
) -> TeamPublic:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    if event.end_at < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This event's deadline has passed.")
    already = _team_in_event(session, user.id, event_id)
    if already:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You are already on a team for this event ({already.name}). "
            "Leave that team before creating another one.",
        )
    team = Team(event_id=event_id, name=payload.name)
    session.add(team)
    session.commit()
    session.refresh(team)
    session.add(TeamMembership(team_id=team.id, user_id=user.id))
    record(session, "team.created", actor=user, entity_type="team", entity_id=team.id, name=team.name)
    session.commit()
    return _team_public(session, team)


@router.post("/api/teams/join", response_model=TeamPublic)
def join_team(
    payload: TeamJoin,
    user: User = Depends(require_role(Role.participant)),
    session: Session = Depends(get_session),
) -> TeamPublic:
    team = session.exec(select(Team).where(Team.invite_code == payload.invite_code)).first()
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That invite link is not valid.")
    if team.invite_code_expires_at < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That invite link has expired.")
    existing = session.exec(
        select(TeamMembership).where(TeamMembership.team_id == team.id, TeamMembership.user_id == user.id)
    ).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already a member of this team.")
    already = _team_in_event(session, user.id, team.event_id)
    if already:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You are already on a team for this event ({already.name}). "
            "Leave that team before joining another one.",
        )
    event = session.get(Event, team.event_id)
    max_size = event.max_team_size if event else 4
    current_size = len(session.exec(select(TeamMembership).where(TeamMembership.team_id == team.id)).all())
    if current_size >= max_size:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This team is full (max {max_size} members).")
    session.add(TeamMembership(team_id=team.id, user_id=user.id))
    record(session, "team.invite_redeemed", actor=user, entity_type="team", entity_id=team.id)
    session.commit()
    return _team_public(session, team)


@router.get("/api/teams/mine", response_model=list[TeamPublic])
def my_teams(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[TeamPublic]:
    memberships = session.exec(select(TeamMembership).where(TeamMembership.user_id == user.id)).all()
    teams = [session.get(Team, m.team_id) for m in memberships]
    return [_team_public(session, t) for t in teams if t]


@router.get("/api/teams/{team_id}", response_model=TeamPublic)
def get_team(
    team_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TeamPublic:
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found.")
    is_member = session.exec(
        select(TeamMembership).where(TeamMembership.team_id == team_id, TeamMembership.user_id == user.id)
    ).first()
    if not is_member and user.role not in (Role.organizer, Role.admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to view this team.")
    return _team_public(session, team)
