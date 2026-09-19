"""Session cookies signed with itsdangerous (PLAN.md section 5)."""
import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-only-not-a-real-secret")
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
