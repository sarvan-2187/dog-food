"""Webhooks against a real HTTP receiver, and a sweep of every API route
(task 5: check the working of the webhooks and the APIs)."""
import json
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.routing import APIRoute
from sqlmodel import select

from app.auth.models import Role, User
from app.auth.session import create_session_token
from app.crypto import verify_record
from app.events.models import Event
from app.timeutil import utcnow
from app.webhooks.models import WebhookSubscription
from app.webhooks.service import _deliver


class _Receiver:
    """A real HTTP server on a free local port that records what it is sent."""

    def __init__(self, status: int = 200, location: "str | None" = None):
        received = self.received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers.get("content-length", 0)))
                received.append((self.path, self.headers.get("content-type"), json.loads(body)))
                self.send_response(status)
                if location:
                    self.send_header("Location", location)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/hook"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture()
def receiver():
    r = _Receiver()
    yield r
    r.close()


def _organizer(client, session) -> User:
    user = User(email="live-wh-org@example.com", name="Org", role=Role.organizer, password_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    client.cookies.set("session", create_session_token(user.id, user.session_version))
    return user


def _event(session, organizer: User, slug: str = "live-wh") -> Event:
    event = Event(slug=slug, name="Live Webhooks", start_at=utcnow() - timedelta(days=1),
                  end_at=utcnow() + timedelta(days=1), created_by_id=organizer.id)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def test_a_real_receiver_gets_a_signed_payload_that_verifies(client, session, receiver, webhook_deliveries):
    organizer = _organizer(client, session)
    event = _event(session, organizer)
    r = client.post(f"/api/events/{event.id}/webhooks", json={"url": receiver.url})
    assert r.status_code == 201
    webhook_id = r.json()["id"]
    # An audited action on the event (any would do): publishing it.
    assert client.post(f"/api/events/{event.id}/publish").status_code == 200

    topics = [signed["record"]["topic"] for _, _, signed in webhook_deliveries]
    assert "webhook.created" in topics and "event.published" in topics
    for url, sub_id, signed in webhook_deliveries:
        _deliver(url, sub_id, signed, session=session)

    assert [body["record"]["topic"] for _, _, body in receiver.received] == topics
    public_key = client.get("/api/public-key").json()["public_key"]
    for path, content_type, body in receiver.received:
        assert path == "/hook"
        assert content_type == "application/json"
        # Verified against the key the server publishes, not the one in the body.
        assert verify_record(body["record"], body["signature"], public_key)
        assert body["record"]["event_id"] == event.id
        assert len(body["record"]["delivery_id"]) == 24
    assert len({b["record"]["delivery_id"] for _, _, b in receiver.received}) == len(receiver.received)
    session.refresh(session.get(WebhookSubscription, webhook_id))
    assert session.get(WebhookSubscription, webhook_id).last_status == "delivered"


def test_a_tampered_payload_does_not_verify(client, session, receiver, webhook_deliveries):
    organizer = _organizer(client, session)
    event = _event(session, organizer, "live-wh-tamper")
    client.post(f"/api/events/{event.id}/webhooks", json={"url": receiver.url})
    url, sub_id, signed = webhook_deliveries[0]
    _deliver(url, sub_id, signed, session=session)
    body = receiver.received[0][2]
    public_key = client.get("/api/public-key").json()["public_key"]
    body["record"]["event_id"] = 999
    assert not verify_record(body["record"], body["signature"], public_key)


@pytest.mark.parametrize("status,expected", [(200, "delivered"), (204, "delivered"), (500, "failed"),
                                            (404, "failed"), (302, "failed")])
def test_delivery_status_follows_the_receivers_answer(session, status, expected):
    organizer = User(email=f"wh-status-{status}@example.com", name="Org", role=Role.organizer, password_hash="x")
    session.add(organizer)
    session.commit()
    event = _event(session, organizer, f"wh-status-{status}")
    sink = _Receiver()  # where a redirect would lead, if it were followed
    r = _Receiver(status=status, location=sink.url if status == 302 else None)
    try:
        webhook = WebhookSubscription(event_id=event.id, url=r.url, created_by_id=organizer.id)
        session.add(webhook)
        session.commit()
        _deliver(webhook.url, webhook.id, {"record": {"topic": "t"}, "signature": "", "public_key": ""}, session=session)
        session.refresh(webhook)
        assert webhook.last_status == expected
        assert sink.received == [], "a redirect must never be followed"
    finally:
        r.close()
        sink.close()


def test_a_malformed_url_records_failed_instead_of_raising(session):
    organizer = User(email="wh-bad-url@example.com", name="Org", role=Role.organizer, password_hash="x")
    session.add(organizer)
    session.commit()
    event = _event(session, organizer, "wh-bad-url")
    webhook = WebhookSubscription(event_id=event.id, url="http://[::1/broken", created_by_id=organizer.id)
    session.add(webhook)
    session.commit()
    _deliver(webhook.url, webhook.id, {"record": {}}, session=session)  # must not raise
    session.refresh(webhook)
    assert webhook.last_status == "failed"


def test_a_deleted_webhook_is_not_told_about_its_own_deletion(client, session, webhook_deliveries):
    organizer = _organizer(client, session)
    event = _event(session, organizer, "wh-del-self")
    keep = client.post(f"/api/events/{event.id}/webhooks", json={"url": "https://keep.example.com/h"}).json()
    gone = client.post(f"/api/events/{event.id}/webhooks", json={"url": "https://gone.example.com/h"}).json()
    webhook_deliveries.clear()
    assert client.delete(f"/api/events/{event.id}/webhooks/{gone['id']}").status_code == 204
    assert [(url, signed["record"]["topic"]) for url, _, signed in webhook_deliveries] == [
        ("https://keep.example.com/h", "webhook.deleted")
    ]
    assert keep["id"] != gone["id"]


# --- every API route answers without a server error ---------------------------

def _routes():
    from app.main import app

    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith(("/api", "/embed", "/healthz")):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                yield method, route.path


def _fill(path: str) -> str:
    import re

    return re.sub(r"\{[^}]+\}", "1", path)


def test_api_surface_is_documented():
    from app.main import app

    spec = app.openapi()
    documented = {(m.upper(), p) for p, ops in spec["paths"].items() for m in ops}
    hidden = {r.path for r in app.routes if isinstance(r, APIRoute) and not r.include_in_schema}
    missing = [(m, p) for m, p in _routes() if (m, p) not in documented and p not in hidden]
    assert not missing, f"routes missing from OpenAPI: {missing}"
    assert len(documented) > 100


@pytest.mark.parametrize("as_role", [None, Role.participant, Role.judge, Role.organizer, Role.admin])
def test_no_route_returns_a_server_error(client, session, as_role, monkeypatch):
    """Every route, with placeholder ids and an empty body, for every role:
    refusals and not-founds are fine, a 5xx never is."""
    from app import request_limit

    monkeypatch.setattr(request_limit.client_limiter, "limit", 0)
    if as_role is not None:
        user = User(email=f"sweep-{as_role.value}@example.com", name="Sweep", role=as_role, password_hash="x")
        session.add(user)
        session.commit()
        client.cookies.set("session", create_session_token(user.id, user.session_version))
    failures = []
    for method, path in _routes():
        if path.endswith("/logout"):
            continue
        r = client.request(method, _fill(path), json={} if method in ("POST", "PUT", "PATCH") else None)
        if r.status_code >= 500:
            failures.append((method, path, r.status_code, r.text[:200]))
    assert not failures, failures


def test_anonymous_callers_are_refused_on_every_mutating_route(client):
    """Nothing that changes data works without an identity, except the few
    routes that exist to create one or to take an anonymous vote."""
    open_by_design = {
        "/api/auth/register", "/api/auth/login", "/api/auth/logout", "/api/auth/forgot-password",
        "/api/auth/reset/{token}", "/api/submissions/{submission_id}/vote", "/api/voter/email",
        "/api/judge-invites/{token}/accept",
    }
    leaks = []
    for method, path in _routes():
        if method == "GET" or path in open_by_design or "reset" in path or "voter" in path:
            continue
        r = client.request(method, _fill(path), json={} if method in ("POST", "PUT", "PATCH") else None)
        if r.status_code < 400:
            leaks.append((method, path, r.status_code))
    assert not leaks, leaks


@pytest.mark.parametrize("as_role", [None, Role.participant, Role.judge, Role.organizer])
def test_no_route_errors_on_real_fixture_data(client, session, as_role, monkeypatch):
    """The same sweep with the official fixtures seeded and every path id
    pointing at a real row, so handlers get past their 404 checks. Only GETs:
    the mutating routes are exercised with valid bodies by their own tests."""
    import re
    from pathlib import Path

    from app import request_limit
    from app.judging.models import JudgeAssignment
    from app.seed import DOGFOOD_EVENT_SLUG, _seed_dogfood
    from app.submissions.models import Submission
    from app.teams.models import Team, TeamMembership

    monkeypatch.setattr(request_limit.client_limiter, "limit", 0)
    here = Path(__file__).resolve()
    path = next((p for p in (here.parents[2] / "fixtures.json", here.parents[1] / "fixtures" / "dogfood.json")
                 if p.exists()), None)
    if path is None:
        pytest.skip("fixtures not found")
    org = User(email="sweep-seed-org@example.com", name="Org", role=Role.organizer, password_hash="x")
    session.add(org)
    session.commit()
    _seed_dogfood(session, path)
    session.commit()
    event = session.exec(select(Event).where(Event.slug == DOGFOOD_EVENT_SLUG)).one()
    assignment = session.exec(select(JudgeAssignment).where(JudgeAssignment.event_id == event.id)).first()
    team = session.exec(select(Team).where(Team.event_id == event.id)).first()
    member = session.exec(select(TeamMembership).where(TeamMembership.team_id == team.id)).first()
    submission = session.exec(select(Submission).where(Submission.team_id == team.id)).first()
    ids = {
        "event_id": event.id, "submission_id": submission.id, "team_id": team.id,
        "assignment_id": assignment.id, "judge_id": assignment.judge_id, "judge_ref": assignment.judge_id,
        "user_id": member.user_id, "member_id": member.user_id, "slug": event.slug,
    }
    if as_role is Role.judge:
        client.cookies.set("session", create_session_token(assignment.judge_id, 0))
    elif as_role is Role.participant:
        client.cookies.set("session", create_session_token(member.user_id, 0))
    elif as_role is Role.organizer:
        client.cookies.set("session", create_session_token(org.id, 0))
    failures = []
    for method, route in _routes():
        if method != "GET":
            continue
        url = re.sub(r"\{([^}:]+)(:[^}]*)?\}", lambda m: str(ids.get(m.group(1), 1)), route)
        r = client.get(url)
        if r.status_code >= 500:
            failures.append((route, r.status_code, r.text[:200]))
    assert not failures, failures
