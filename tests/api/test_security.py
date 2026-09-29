"""Security audit fixes (task 7). docs/audit/SECURITY-AUDIT.md lists each one."""
import csv
import io
import os
import stat
from datetime import timedelta

import pytest
from sqlmodel import select

from app.auth.models import Role, User
from app.auth.session import create_session_token
from app.events.models import Event
from app.timeutil import utcnow


def _as(client, session, email: str, role: Role) -> User:
    user = User(email=email, name=email.split("@")[0], role=role, password_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    client.cookies.set("session", create_session_token(user.id, user.session_version))
    return user


def _event(session, owner: User, slug: str) -> Event:
    event = Event(slug=slug, name="Sec Event", start_at=utcnow() - timedelta(days=3),
                  end_at=utcnow() - timedelta(days=1), created_by_id=owner.id)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


# --- S1 session secret --------------------------------------------------------

def test_no_hard_coded_session_secret_fallback(tmp_path, monkeypatch):
    import importlib

    import app.auth.session as session_mod

    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.setenv("KEYS_DIR", str(tmp_path))
    try:
        first = session_mod._load_session_secret()
        assert first not in session_mod.PUBLISHED_SECRETS and len(first) >= 48
        path = tmp_path / "session-secret"
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        assert session_mod._load_session_secret() == first, "persisted across restarts"
    finally:
        importlib.reload(session_mod) if False else None


def test_explicit_secret_wins(monkeypatch, tmp_path):
    import app.auth.session as session_mod

    monkeypatch.setenv("SESSION_SECRET", "a-long-operator-chosen-secret-value")
    monkeypatch.setenv("KEYS_DIR", str(tmp_path))
    assert session_mod._load_session_secret() == "a-long-operator-chosen-secret-value"
    assert not (tmp_path / "session-secret").exists()


def test_malformed_signed_payload_is_not_a_session():
    from app.auth import session as session_mod

    token = session_mod._serializer.dumps(["not", "a", "dict"])
    assert session_mod.read_session_token(token) is None
    assert session_mod.read_session_token(session_mod._serializer.dumps({"user_id": "1"})) is None


# --- S2 cookie flags ------------------------------------------------------------

@pytest.mark.parametrize("base,override,expected", [
    ("https://hackflow.example.org", "", True),
    ("http://localhost:8000", "", False),
    ("", "", False),
    ("http://localhost:8000", "1", True),
    ("https://hackflow.example.org", "0", False),
])
def test_cookie_secure_follows_https(monkeypatch, base, override, expected):
    from app.auth import session as session_mod

    monkeypatch.setenv("APP_BASE_URL", base)
    monkeypatch.setenv("COOKIE_SECURE", override)
    assert session_mod._cookie_secure() is expected


def test_session_cookie_is_httponly_and_samesite(client):
    r = client.post("/api/auth/register", json={"email": "cookie@example.com", "password": "supersecret1",
                                                "name": "Cookie"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_secure_flag_is_set_when_configured(client, monkeypatch):
    monkeypatch.setattr("app.auth.router.COOKIE_SECURE", True)
    r = client.post("/api/auth/register", json={"email": "securecookie@example.com", "password": "supersecret1",
                                                "name": "Secure"})
    assert "secure" in r.headers["set-cookie"].lower()


# --- S3 key file permissions -------------------------------------------------

def test_signing_key_is_created_private(tmp_path, monkeypatch):
    import app.crypto as crypto

    monkeypatch.setattr(crypto, "KEYS_DIR", tmp_path)
    monkeypatch.setattr(crypto, "_PRIVATE_KEY_PATH", tmp_path / "k.pem")
    crypto._load_or_create_key()
    assert stat.S_IMODE(os.stat(tmp_path / "k.pem").st_mode) == 0o600


# --- S4 webhook SSRF -------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:5432/", "http://localhost/hook", "http://10.0.0.5/x", "http://192.168.1.10/x",
    "http://172.16.0.1/x", "http://169.254.169.254/latest/meta-data/", "http://[::1]/x", "http://0.0.0.0/x",
    "http://100.64.0.1/x", "http://[::ffff:127.0.0.1]/x", "http://user:pw@example.com/x", "ftp://example.com/x",
])
def test_webhooks_to_internal_addresses_are_refused(client, session, url):
    org = _as(client, session, f"ssrf-{abs(hash(url))}@example.com", Role.organizer)
    event = _event(session, org, f"ssrf-{abs(hash(url))}")
    r = client.post(f"/api/events/{event.id}/webhooks", json={"url": url})
    assert r.status_code == 422, (url, r.text)


def test_public_webhook_targets_are_accepted(client, session):
    org = _as(client, session, "ssrf-ok@example.com", Role.organizer)
    event = _event(session, org, "ssrf-ok")
    assert client.post(f"/api/events/{event.id}/webhooks", json={"url": "https://hooks.example.com/x"}).status_code == 201


def test_opt_in_allows_local_receivers(client, session, monkeypatch):
    monkeypatch.setenv("WEBHOOK_ALLOW_PRIVATE", "1")
    org = _as(client, session, "ssrf-optin@example.com", Role.organizer)
    event = _event(session, org, "ssrf-optin")
    assert client.post(f"/api/events/{event.id}/webhooks", json={"url": "http://127.0.0.1:9/x"}).status_code == 201


def test_delivery_rechecks_the_target(session, monkeypatch):
    """A name that resolved publicly at creation but privately now is not called."""
    from app.webhooks import service, targets
    from app.webhooks.models import WebhookSubscription

    calls = []
    monkeypatch.setattr(service.httpx, "post", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(targets, "_resolve", lambda host, port: ["10.1.2.3"])
    org = User(email="rebind@example.com", name="Org", role=Role.organizer, password_hash="x")
    session.add(org)
    session.commit()
    event = _event(session, org, "rebind")
    hook = WebhookSubscription(event_id=event.id, url="https://rebind.example.com/x", created_by_id=org.id)
    session.add(hook)
    session.commit()
    service._deliver(hook.url, hook.id, {"record": {}}, session=session)
    session.refresh(hook)
    assert calls == [] and hook.last_status == "blocked"


# --- S5 CSV injection ---------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("=HYPERLINK(\"http://evil\")", "'=HYPERLINK(\"http://evil\")"), ("+1", "'+1"), ("-2", "'-2"),
    ("@SUM(A1)", "'@SUM(A1)"), ("\tx", "'\tx"), ("Normal title", "Normal title"), (-3.5, -3.5), (7, 7),
])
def test_csv_cells_cannot_be_formulas(value, expected):
    from app.scoring.router import _csv_safe

    assert _csv_safe(value) == expected


def test_exported_csv_neutralises_a_formula_title(client, session):
    from app.submissions.models import Submission, SubmissionStatus
    from app.teams.models import Team

    org = _as(client, session, "csvinj-org@example.com", Role.organizer)
    event = _event(session, org, "csvinj")
    team = Team(event_id=event.id, name="=cmd|' /C calc'!A0")
    session.add(team)
    session.commit()
    session.add(Submission(team_id=team.id, event_id=event.id, title="=1+1", description="x",
                           status=SubmissionStatus.submitted))
    session.commit()
    body = client.get(f"/api/events/{event.id}/export/submissions.csv").text
    row = list(csv.reader(io.StringIO(body)))[1]
    assert row[1] == "'=1+1" and row[3].startswith("'=")


# --- S6 users export scoped to the event ------------------------------------------

def test_users_export_lists_only_this_events_people(client, session):
    from app.judging.models import EventJudge
    from app.teams.models import Team, TeamMembership

    org = _as(client, session, "scope-org@example.com", Role.organizer)
    event = _event(session, org, "scope-a")
    other = _event(session, org, "scope-b")
    mine = User(email="scope-member@example.com", name="Mine", role=Role.participant, password_hash="x")
    judge = User(email="scope-judge@example.com", name="Judge", role=Role.judge, password_hash="x")
    stranger = User(email="scope-stranger@example.com", name="Stranger", role=Role.participant, password_hash="x")
    session.add_all([mine, judge, stranger])
    session.commit()
    t1, t2 = Team(event_id=event.id, name="A"), Team(event_id=other.id, name="B")
    session.add_all([t1, t2])
    session.commit()
    session.add_all([TeamMembership(team_id=t1.id, user_id=mine.id), TeamMembership(team_id=t2.id, user_id=stranger.id),
                     EventJudge(event_id=event.id, user_id=judge.id)])
    session.commit()
    emails = {r["email"] for r in csv.DictReader(io.StringIO(client.get(f"/api/events/{event.id}/export/users.csv").text))}
    assert emails == {"scope-member@example.com", "scope-judge@example.com"}


# --- S7 headers -------------------------------------------------------------------------

def test_hsts_only_over_https(client):
    assert "strict-transport-security" not in client.get("/healthz").headers
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, base_url="https://testserver") as https_client:
        assert "max-age=" in https_client.get("/healthz").headers["strict-transport-security"]


def test_early_refusals_are_not_framable(client, monkeypatch):
    from app import request_limit

    monkeypatch.setattr(request_limit.client_limiter, "limit", 1)
    client.get("/api/gallery")
    r = client.get("/api/gallery")
    assert r.status_code == 429 and r.headers["x-frame-options"] == "DENY"


# --- S8 password length ------------------------------------------------------------------

def test_passwords_beyond_bcrypts_72_bytes_are_refused(client):
    r = client.post("/api/auth/register", json={"email": "longpw@example.com", "password": "x" * 73, "name": "Long"})
    assert r.status_code == 422
    r = client.post("/api/auth/register", json={"email": "okpw@example.com", "password": "x" * 72, "name": "Ok"})
    assert r.status_code == 201


# --- S9 client address behind a proxy -------------------------------------------

def _client_seen(hops, xff):
    import asyncio

    from app.protection import TrustedProxyMiddleware

    seen = {}

    async def app(scope, receive, send):
        seen["client"] = scope["client"][0]

    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    scope = {"type": "http", "path": "/", "headers": headers, "client": ("10.0.0.1", 1234)}
    asyncio.run(TrustedProxyMiddleware(app, hops=hops)(scope, None, None))
    return seen["client"]


def test_forwarded_for_is_ignored_by_default():
    assert _client_seen(0, "1.2.3.4") == "10.0.0.1"


def test_only_the_trusted_hop_counts_not_a_spoofed_leftmost_entry():
    # The client sent "6.6.6.6"; Render appended the real address 203.0.113.9.
    assert _client_seen(1, "6.6.6.6, 203.0.113.9") == "203.0.113.9"
    assert _client_seen(1, "203.0.113.9") == "203.0.113.9"
    assert _client_seen(2, "6.6.6.6, 198.51.100.7, 203.0.113.9") == "198.51.100.7"
    assert _client_seen(1, None) == "10.0.0.1"
