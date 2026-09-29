"""Session cookies signed with itsdangerous (PLAN.md section 5)."""
import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import logging

DEV_SECRET = "dev-only-not-a-real-secret"
SESSION_SECRET = os.getenv("SESSION_SECRET", DEV_SECRET)
if SESSION_SECRET == DEV_SECRET or len(SESSION_SECRET) < 16:
    # Anyone who knows this value can forge a session for any account. Fine on
    # a laptop demo; on a public address it is a full takeover.
    logging.getLogger(__name__).warning(
        "SESSION_SECRET is the public development default (or too short). "
        "Set a long random value before exposing HackFlow to the internet."
    )

# Secure cookies only travel over https. On by default when the public address
# is https (APP_BASE_URL); COOKIE_SECURE=1/0 overrides either way.
_secure_env = os.getenv("COOKIE_SECURE", "").strip().lower()
COOKIE_SECURE = (
    _secure_env in ("1", "true", "yes")
    if _secure_env
    else os.getenv("APP_BASE_URL", "").strip().lower().startswith("https://")
)
SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

_serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="dogfood-session")


def create_session_token(user_id: int, version: int = 0) -> str:
    return _serializer.dumps({"user_id": user_id, "v": version})


def read_session_token(token: str) -> "tuple[int, int] | None":
    """(user_id, session_version). A cookie signed before Phase 9.1 has no "v"
    and reads as version 0, so existing sessions survive the upgrade."""
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    user_id = data.get("user_id")
    if user_id is None:
        return None
    return user_id, data.get("v", 0)
