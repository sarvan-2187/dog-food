from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, get_current_user, require_role
from ..db import get_session
from ..events.models import Event
from ..timeutil import utcnow
from .deps import require_team_member
from ..storage.models import StoredFile
from ..storage.service import storage
from ..submissions.models import Submission, SubmissionStatus
from .models import Team, TeamMembership, _default_expiry, _invite_code
from .schemas import CaptainChange, TeamCreate, TeamJoin, TeamMemberPublic, TeamPublic, TeamRename

router = APIRouter(tags=["teams"])


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
        captain_id=team.captain_id,
        invite_code_expires_at=team.invite_code_expires_at,
    )


def _team_in_event(session: Session, event_id: int, user_id: int) -> "Team | None":
    """The team `user_id` is already on in this event, if any (PLAN.md 10.2)."""
    return session.exec(
        select(Team)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .where(Team.event_id == event_id, TeamMembership.user_id == user_id)
    ).first()


def _already_on_a_team(team: Team) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        f"You're already on {team.name} for this event. Leave it first to join another team.",
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
    if event.status != "published":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    if event.end_at < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This event's deadline has passed.")
    if existing_team := _team_in_event(session, event_id, user.id):
        raise _already_on_a_team(existing_team)
    team = Team(event_id=event_id, name=payload.name, captain_id=user.id)
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
    if other := _team_in_event(session, team.event_id, user.id):
        raise _already_on_a_team(other)
    event = session.get(Event, team.event_id)
    if event and event.end_at < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This event's deadline has passed.")
    max_size = event.max_team_size if event else 4
    # Lock the team row before counting, so two people joining at the same
    # moment can't both see "one seat left" and push the team past its cap.
    session.exec(select(Team).where(Team.id == team.id).with_for_update()).one()
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


# --------------------------------------------------------------------------
# Team management (PLAN.md Phase 10.9). Any member may leave; the captain -
# whoever created the team - may rename it, remove members, hand the role on
# and replace the invite link. Nothing changes after the deadline.
# --------------------------------------------------------------------------

def _open_team(session: Session, team: Team) -> Event:
    event = session.get(Event, team.event_id)
    if event is None or event.end_at < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This event's deadline has passed, so the team is locked.")
    return event


def _require_captain(team: Team, user: User) -> None:
    if team.captain_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the team captain can do that.")


def _members(session: Session, team_id: int) -> list[TeamMembership]:
    return list(
        session.exec(
            select(TeamMembership).where(TeamMembership.team_id == team_id).order_by(TeamMembership.joined_at, TeamMembership.id)
        )
    )


def _delete_team(session: Session, team: Team) -> None:
    """Only ever reached for a team whose entry was never submitted, so nothing
    judged, voted on or commented on is lost - just a draft and its image."""
    submission = session.exec(select(Submission).where(Submission.team_id == team.id)).first()
    if submission is not None:
        for stored in session.exec(
            select(StoredFile).where(StoredFile.owner_type == "submission", StoredFile.owner_id == submission.id)
        ):
            storage.delete(stored.key)
            session.delete(stored)
        session.delete(submission)
    session.delete(team)


def _remove_member(session: Session, team: Team, membership: TeamMembership) -> bool:
    """Returns True if the team was deleted because nobody was left."""
    remaining = [m for m in _members(session, team.id) if m.id != membership.id]
    if not remaining:
        submitted = session.exec(
            select(Submission).where(Submission.team_id == team.id, Submission.status == SubmissionStatus.submitted)
        ).first()
        if submitted is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "You're the last member and your team has already submitted, so leaving would abandon that entry. "
                "Ask an organizer if you need it withdrawn.",
            )
    session.delete(membership)
    session.flush()
    if not remaining:
        _delete_team(session, team)
        return True
    if team.captain_id == membership.user_id:
        team.captain_id = remaining[0].user_id  # earliest remaining member
        session.add(team)
    return False


@router.post("/api/teams/{team_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_team(
    team_id: int,
    user: User = Depends(get_current_user),
    team: Team = Depends(require_team_member),
    session: Session = Depends(get_session),
) -> None:
    _open_team(session, team)
    membership = session.exec(
        select(TeamMembership).where(TeamMembership.team_id == team_id, TeamMembership.user_id == user.id)
    ).one()
    deleted = _remove_member(session, team, membership)
    record(session, "team.left", actor=user, entity_type="team", entity_id=team_id, team_deleted=deleted)
    session.commit()


@router.delete("/api/teams/{team_id}/members/{member_id}", response_model=TeamPublic)
def remove_member(
    team_id: int,
    member_id: int,
    user: User = Depends(get_current_user),
    team: Team = Depends(require_team_member),
    session: Session = Depends(get_session),
) -> TeamPublic:
    _open_team(session, team)
    _require_captain(team, user)
    if member_id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "To take yourself off the team, use Leave team instead.")
    membership = session.exec(
        select(TeamMembership).where(TeamMembership.team_id == team_id, TeamMembership.user_id == member_id)
    ).first()
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That person isn't on this team.")
    _remove_member(session, team, membership)
    record(session, "team.member_removed", actor=user, entity_type="team", entity_id=team_id, removed_user_id=member_id)
    session.commit()
    session.refresh(team)
    return _team_public(session, team)


@router.patch("/api/teams/{team_id}", response_model=TeamPublic)
def rename_team(
    team_id: int,
    payload: TeamRename,
    user: User = Depends(get_current_user),
    team: Team = Depends(require_team_member),
    session: Session = Depends(get_session),
) -> TeamPublic:
    _open_team(session, team)
    _require_captain(team, user)
    old_name = team.name
    team.name = payload.name
    session.add(team)
    record(session, "team.renamed", actor=user, entity_type="team", entity_id=team_id, old_name=old_name, name=team.name)
    session.commit()
    session.refresh(team)
    return _team_public(session, team)


@router.post("/api/teams/{team_id}/captain", response_model=TeamPublic)
def change_captain(
    team_id: int,
    payload: CaptainChange,
    user: User = Depends(get_current_user),
    team: Team = Depends(require_team_member),
    session: Session = Depends(get_session),
) -> TeamPublic:
    _open_team(session, team)
    _require_captain(team, user)
    if not any(m.user_id == payload.user_id for m in _members(session, team_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That person isn't on this team.")
    team.captain_id = payload.user_id
    session.add(team)
    record(session, "team.captain_changed", actor=user, entity_type="team", entity_id=team_id, captain_id=payload.user_id)
    session.commit()
    session.refresh(team)
    return _team_public(session, team)


@router.post("/api/teams/{team_id}/invite-code", response_model=TeamPublic)
def new_invite_code(
    team_id: int,
    user: User = Depends(get_current_user),
    team: Team = Depends(require_team_member),
    session: Session = Depends(get_session),
) -> TeamPublic:
    """The old link stops working at once - for a link that went further than
    intended, or one that expired."""
    _open_team(session, team)
    _require_captain(team, user)
    team.invite_code = _invite_code()
    team.invite_code_expires_at = _default_expiry()
    session.add(team)
    record(session, "team.invite_code_changed", actor=user, entity_type="team", entity_id=team_id)
    session.commit()
    session.refresh(team)
    return _team_public(session, team)
