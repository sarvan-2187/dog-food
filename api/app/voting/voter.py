"""Who is voting, under an event's voting_access (DOGFOOD T3: "open link,
email-gated, or authenticated").

Every vote carries a voter_key. A signed-in account and a guest who confirmed
the same address share one key ("email:<hash>"), so the unique index on
(voter_key, submission_id) stops one address voting twice across both paths.
Open-link guests get a random "anon:" key in a signed cookie - clearing cookies
mints a new voter, which is the documented ceiling of "open" (THREAT-MODEL.md).

Email confirmation is stateless: the emailed link carries a signed, timed
(event, email) pair, so there is no token table to clean up.
"""
from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from fastapi import HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..auth.models import User
from ..auth.session import COOKIE_SECURE, SESSION_SECRET
from ..events.models import Event

VOTER_COOKIE = "voter"
VOTER_MAX_AGE = 60 * 60 * 24 * 30  # a voting window rarely outlives a month
EMAIL_LINK_MAX_AGE = 30 * 60

ACCESS_MODES = ("authenticated", "email", "open")

_cookie = URLSafeTimedSerializer(SESSION_SECRET, salt="dogfood-voter")
_email_link = URLSafeTimedSerializer(SESSION_SECRET, salt="dogfood-voter-email")


def email_key(email: str) -> str:
    """Must match the SQL backfill in app.db.add_vote_voter_index."""
    return "email:" + hashlib.sha256(email.strip().lower().encode()).hexdigest()[:32]


def read_voter_key(request: Request) -> Optional[str]:
    token = request.cookies.get(VOTER_COOKIE)
    if not token:
        return None
    try:
        return _cookie.loads(token, max_age=VOTER_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def set_voter_cookie(response: Response, key: str) -> None:
    response.set_cookie(
        VOTER_COOKIE, _cookie.dumps(key), max_age=VOTER_MAX_AGE, httponly=True, samesite="lax",
        secure=COOKIE_SECURE,
    )


def email_link_token(event_id: int, email: str) -> str:
    return _email_link.dumps({"e": event_id, "m": email.strip().lower()})


def read_email_link_token(token: str) -> Optional[tuple[int, str]]:
    try:
        data = _email_link.loads(token, max_age=EMAIL_LINK_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data["e"], data["m"]


def resolve_voter(
    event: Event, request: Request, response: Response, user: Optional[User], *, mint: bool
) -> tuple[Optional[User], str]:
    """(account or None, voter_key), or 401 naming what this event needs.

    A signed-in account always votes as itself, whatever the mode. `mint` lets
    an open-link guest with no cookie yet become a voter (casting); withdrawing
    passes False, since a new voter has nothing to withdraw.
    """
    if user is not None:
        return user, email_key(user.email)
    key = read_voter_key(request)
    access = event.voting_access
    if access == "open":
        if key is None and mint:
            key = "anon:" + secrets.token_urlsafe(16)
            set_voter_cookie(response, key)
        if key is not None:
            return None, key
    elif access == "email" and key is not None and key.startswith("email:"):
        return None, key
    if access == "email":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Confirm your email address to vote in this event.")
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Log in to vote.")
