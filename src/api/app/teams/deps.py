"""Shared team-membership guard, reused by the submissions router."""
from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from ..auth import User, get_current_user
from ..db import get_session
from .models import Team, TeamMembership


def require_team_member(
    team_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Team:
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found.")
    is_member = session.exec(
        select(TeamMembership).where(
            TeamMembership.team_id == team_id,
            TeamMembership.user_id == user.id,
        )
    ).first()
    if not is_member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of this team.")
    return team
