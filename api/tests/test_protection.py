"""Request-level protection (app/protection.py) and the audit's other fixes
(docs/SECURITY-AUDIT.md): global rate limits, body caps, security headers,
proxy-aware client addresses, case-insensitive email, sign-up throttling,
track validation and the frozen legacy image upload."""
from datetime import timedelta

import pytest
from sqlmodel import select

from app import protection
from app.auth.models import Role, User
from app.events.models import Event
from app.ratelimit import TokenBucketLimiter
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _register(client, email, password="supersecret1", name="Test Person"):
    return client.post("/api/auth/register", json={"email": email, "password": password, "name": name})


# --- global limiter -----------------------------------------------------------

def test_reads_are_limited_per_address_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(protection, "request_limiter", TokenBucketLimiter(capacity=5, per_seconds=60.0))
    codes = [client.get("/api/events").status_code for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429
    r = client.get("/api/events")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert "slow down" in r.json()["detail"]


def test_healthz_is_never_limited(client, monkeypatch):
    monkeypatch.setattr(protection, "request_limiter", TokenBucketLimiter(capacity=1, per_seconds=60.0))
    assert all(client.get("/healthz").status_code == 200 for _ in range(5))


def test_writes_have_a_tighter_bucket(client, monkeypatch):
    monkeypatch.setattr(protection, "write_limiter", TokenBucketLimiter(capacity=2, per_seconds=60.0))
    codes = [client.post("/api/auth/logout").status_code for _ in range(3)]
    assert codes == [204, 204, 429]
    assert client.get("/api/events").status_code == 200, "reads keep working"


def test_an_api_key_has_its_own_bucket(client, monkeypatch):
    monkeypatch.setattr(protection, "request_limiter", TokenBucketLimiter(capacity=1, per_seconds=60.0))
    client.get("/api/events")
    assert client.get("/api/events").status_code == 429
    # A bearer credential is counted per key, not per address.
    assert client.get("/api/events", headers={"Authorization": "Bearer hf_not_a_real_key"}).status_code == 200


def test_the_limiter_never_holds_more_than_max_keys():
    limiter = TokenBucketLimiter(capacity=2, per_seconds=60.0, max_keys=100)
    for i in range(1000):
        limiter.check(f"k{i}", now=float(i))
    assert len(limiter._buckets) <= 100


# --- proxy-aware address ------------------------------------------------------

def _scope(xff: str, client_ip="10.0.0.1"):
    return {"client": (client_ip, 1234), "headers": [(b"x-forwarded-for", xff.encode())]}


def test_forwarded_for_is_ignored_unless_proxies_are_trusted(monkeypatch):
    monkeypatch.setattr(protection, "TRUSTED_PROXY_HOPS", 0)
    assert protection.client_ip_from_scope(_scope("6.6.6.6")) == "10.0.0.1"


def test_with_one_trusted_proxy_the_rightmost_entry_is_the_client(monkeypatch):
    monkeypatch.setattr(protection, "TRUSTED_PROXY_HOPS", 1)
    # The client sent a spoofed "1.1.1.1"; the proxy appended the real address.
    assert protection.client_ip_from_scope(_scope("1.1.1.1, 203.0.113.9")) == "203.0.113.9"


# --- body size + headers ------------------------------------------------------

def test_an_oversized_json_body_is_refused_before_it_is_read(client):
    r = client.post("/api/auth/login", content=b"x" * (protection.DEFAULT_BODY_LIMIT + 1),
                    headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_security_headers_are_on_every_response(client):
    r = client.get("/api/events")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in r.headers["permissions-policy"]
    assert r.headers["x-frame-options"] == "DENY"


# --- accounts -----------------------------------------------------------------

def test_email_case_cannot_create_a_second_account(client, session):
    assert _register(client, "Case.Person@Example.com").status_code == 201
    client.post("/api/auth/logout")
    assert _register(client, "case.person@example.com").status_code == 409
    stored = session.exec(select(User).where(User.email == "case.person@example.com")).first()
    assert stored is not None, "stored lowercased"
    r = client.post("/api/auth/login", json={"email": "CASE.PERSON@example.com", "password": "supersecret1"})
    assert r.status_code == 200


def test_signups_are_throttled_per_address(client):
    codes = [_register(client, f"flood{i}@example.com").status_code for i in range(21)]
    assert codes[:20] == [201] * 20 and codes[20] == 429


# --- submissions --------------------------------------------------------------

def _team_with_event(client, session, *, tracks, open_=True):
    _register(client, "tracker@example.com")
    user = session.exec(select(User).where(User.email == "tracker@example.com")).first()
    now = utcnow()
    event = Event(
        slug=f"trk-{'open' if open_ else 'closed'}", name="Track Event", tracks=tracks,
        start_at=now - timedelta(days=2),
        end_at=now + timedelta(days=1) if open_ else now - timedelta(hours=1),
        created_by_id=user.id,
    )
    session.add(event)
    session.commit()
    team = Team(event_id=event.id, name="Trackers", captain_id=user.id)
    session.add(team)
    session.commit()
    session.add(TeamMembership(team_id=team.id, user_id=user.id))
    session.commit()
    return team


def test_a_submission_track_must_be_one_of_the_events_tracks(client, session):
    team = _team_with_event(client, session, tracks=["AI", "Web"])
    assert client.patch(f"/api/teams/{team.id}/submission", json={"track": "Made Up"}).status_code == 422
    r = client.patch(f"/api/teams/{team.id}/submission", json={"track": "AI"})
    assert r.status_code == 200 and r.json()["track"] == "AI"


def test_the_legacy_image_upload_is_frozen_after_the_deadline(client, session):
    team = _team_with_event(client, session, tracks=[], open_=False)
    from app.submissions.models import Submission

    session.add(Submission(team_id=team.id, event_id=team.event_id, title="Late", description="x"))
    session.commit()
    r = client.post(
        f"/api/teams/{team.id}/submission/image", files={"file": ("a.png", PNG, "image/png")}
    )
    assert r.status_code == 400, r.text


def test_signed_in_users_are_counted_per_account_not_per_address(client, monkeypatch):
    """A venue behind one NAT: one person's heavy use must not throttle the next."""
    monkeypatch.setattr(protection, "request_limiter", TokenBucketLimiter(capacity=8, per_seconds=60.0))
    _register(client, "venue-a@example.com")  # now signed in as A
    for _ in range(8):
        client.get("/api/events")
    assert client.get("/api/events").status_code == 429, "A has spent A's bucket"
    client.cookies.clear()  # B, same address, not signed in yet
    assert client.get("/api/events").status_code == 200, "the address bucket is untouched"


def test_a_forged_session_cookie_falls_back_to_the_address_bucket(client, monkeypatch):
    monkeypatch.setattr(protection, "request_limiter", TokenBucketLimiter(capacity=2, per_seconds=60.0))
    client.cookies.set("session", "forged.value.here")
    codes = [client.get("/api/events").status_code for _ in range(3)]
    client.cookies.clear()
    assert codes[2] == 429 and client.get("/api/events").status_code == 429
