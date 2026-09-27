"""require_role() - implemented once, imported everywhere (PLAN.md section 8)."""
from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from ..db import get_session
from .models import Role, User
from .session import SESSION_COOKIE_NAME, read_session_token


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user_id = read_session_token(token) if token else None
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    return user


def get_current_user_optional(request: Request, session: Session = Depends(get_session)) -> "User | None":
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user_id = read_session_token(token) if token else None
    if user_id is None:
        return None
    return session.get(User, user_id)


def require_role(*roles: Role):
    """Endpoint-level role gate. Never rely on frontend hiding alone (PLAN.md section 1)."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to do this.")
        return user

    return dependency
