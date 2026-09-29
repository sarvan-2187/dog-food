"""Session cookies signed with itsdangerous (PLAN.md section 5)."""
import logging
import os
import secrets
from pathlib import Path

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

log = logging.getLogger("hackflow.session")

# Values that have been published (docker-compose.yml, docs). A server signing
# with one of these accepts cookies anyone can forge, as any account.
PUBLISHED_SECRETS = frozenset({"dev-only-not-a-real-secret", "test-secret-not-for-prod"})


def _load_session_secret() -> str:
    """SESSION_SECRET if set. Otherwise a random secret generated on first boot
    and kept in KEYS_DIR next to the signing key, so it survives restarts
    (certificate serials and live sessions stay valid) without anyone having
    to choose one. There used to be a hard-coded fallback, which meant an
    install that forgot to set the variable accepted forged sessions."""
    explicit = os.getenv("SESSION_SECRET", "").strip()
    if explicit:
        if explicit in PUBLISHED_SECRETS:
            log.warning(
                "SESSION_SECRET is a published example value: anyone can forge sessions. "
                "Unset it (a random one is then generated) or set your own before real use."
            )
        return explicit
    keys_dir = Path(os.getenv("KEYS_DIR", "keys"))
    path = keys_dir / "session-secret"
    if path.exists():
        return path.read_text().strip()
    keys_dir.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_urlsafe(48)
    # Created 0600 from the start, never world-readable even for a moment.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(secret)
    log.info("generated a session secret in %s", path)
    return secret


SESSION_SECRET = _load_session_secret()
SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _cookie_secure() -> bool:
    """Secure cookies whenever the site is served over HTTPS (APP_BASE_URL), so
    a session is never sent in clear text. COOKIE_SECURE=1/0 overrides; plain
    http://localhost keeps working for `docker compose up`."""
    override = os.getenv("COOKIE_SECURE", "").strip().lower()
    if override in ("1", "true", "yes"):
        return True
    if override in ("0", "false", "no"):
        return False
    return os.getenv("APP_BASE_URL", "").strip().lower().startswith("https://")


COOKIE_SECURE = _cookie_secure()

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
    if not isinstance(data, dict):
        return None
    user_id = data.get("user_id")
    if not isinstance(user_id, int):
        return None
    return user_id, data.get("v", 0)
