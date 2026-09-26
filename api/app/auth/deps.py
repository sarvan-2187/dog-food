"""require_role() - implemented once, imported everywhere (PLAN.md section 8)."""
import os

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session, select

from ..db import get_session
from .models import Role, User
from .session import SESSION_COOKIE_NAME, read_session_token

# Fixed, non-expiring session tokens for the DOGFOOD acceptance checker, which
# never logs in (.dogfood.toml [auth]). Format "token=email,token=email".
# Empty unless set, and only docker-compose.yml sets it: never set it on a real
# deployment, since anyone holding a token is that account.
DEMO_SESSION_TOKENS: dict[str, str] = dict(
    pair.strip().split("=", 1) for pair in os.getenv("DEMO_SESSION_TOKENS", "").split(",") if "=" in pair
)


def _user_from_cookie(request: Request, session: Session) -> "User | None":
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token in DEMO_SESSION_TOKENS:
        user = session.exec(select(User).where(User.email == DEMO_SESSION_TOKENS[token])).first()
        return user if user is not None and user.is_active else None
    parsed = read_session_token(token) if token else None
    if parsed is None:
        return None
    user_id, version = parsed
    user = session.get(User, user_id)
    # A version mismatch means the password changed after this cookie was
    # issued: every older session is dead (PLAN.md Phase 9.1).
    if user is None or user.session_version != version or not user.is_active:
        return None
    return user


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    user = _user_from_cookie(request, session)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    return user


def get_current_user_optional(request: Request, session: Session = Depends(get_session)) -> "User | None":
    return _user_from_cookie(request, session)


def require_role(*roles: Role):
    """Endpoint-level role gate. Never rely on frontend hiding alone (PLAN.md section 1)."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to do this.")
        return user

    return dependency
