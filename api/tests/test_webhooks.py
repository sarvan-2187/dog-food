"""Webhook subscription CRUD and signed delivery (PLAN.md Phase 7.3)."""
import asyncio
from datetime import timedelta

from fastapi import BackgroundTasks
from sqlmodel import select

from app.auth.models import Role, User
from app.auth.security import hash_password
from app.crypto import verify_record
from app.events.models import Event
from app.timeutil import utcnow
from app.webhooks.models import WebhookSubscription
from app.webhooks.service import _deliver, notify


def _user(session, email: str, role: Role) -> User:
    user = User(email=email, name=email.split("@")[0], role=role, password_hash=hash_password("supersecret1"))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _login_as(client, session, email: str, role: Role) -> User:
    client.post("/api/auth/logout")
    r = client.post("/api/auth/register", json={"email": email, "password": "supersecret1", "name": email})
    if r.status_code == 409:
        client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    user = session.exec(select(User).where(User.email == email)).first()
    if user.role != role:
        user.role = role
        session.add(user)
        session.commit()
        client.post("/api/auth/logout")
        client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    session.refresh(user)
    return user


def _event(session, slug: str, organizer: User) -> Event:
    event = Event(
        slug=slug, name="Webhook Event",
        start_at=utcnow() - timedelta(days=1), end_at=utcnow() + timedelta(days=1),
        created_by_id=organizer.id,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def _run(session, event_id: int, topic: str, **detail) -> BackgroundTasks:
    """Calls notify() directly and runs the background tasks it queued,
    the same way Starlette runs them after a real request -- this unit-tests
    the delivery mechanism itself rather than re-driving a full
    submission/assignment/score flow just to reach one notify() call."""
    background_tasks = BackgroundTasks()
    notify(session, background_tasks, event_id, topic, **detail)
    asyncio.run(background_tasks())
    return background_tasks


class _FakeResponse:
    def __init__(self, ok: bool):
        self.is_success = ok


def test_organizer_can_create_list_and_delete_a_webhook(client, session):
    organizer = _login_as(client, session, "wh-crud-org@example.com", Role.organizer)
    event = _event(session, "wh-crud", organizer)

    created = client.post(f"/api/events/{event.id}/webhooks", json={"url": "https://example.com/hook"})
    assert created.status_code == 201, created.text
    assert created.json()["last_status"] == "never fired"

    listed = client.get(f"/api/events/{event.id}/webhooks")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = client.delete(f"/api/events/{event.id}/webhooks/{created.json()['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/events/{event.id}/webhooks").json() == []


def test_a_participant_cannot_create_a_webhook(client, session):
    organizer = _user(session, "wh-perm-org@example.com", Role.organizer)
    event = _event(session, "wh-perm", organizer)
    _login_as(client, session, "wh-perm-participant@example.com", Role.participant)
    r = client.post(f"/api/events/{event.id}/webhooks", json={"url": "https://example.com/hook"})
    assert r.status_code == 403


def test_webhook_url_must_look_like_a_url(client, session):
    organizer = _login_as(client, session, "wh-badurl-org@example.com", Role.organizer)
    event = _event(session, "wh-badurl", organizer)
    r = client.post(f"/api/events/{event.id}/webhooks", json={"url": "not-a-url"})
    assert r.status_code == 422


def test_delivery_sends_a_signed_payload_that_verifies(session, monkeypatch):
    """notify() -> background_tasks proves the enqueue path fires with the
    right payload; the status-recording half is unit-tested separately below
    via _deliver(session=...), since a real background task deliberately
    opens a fresh DB connection in production (the request's own session is
    already closed by then) -- which this test harness's per-test savepoint
    transaction can never make visible to a second connection. Passing the
    test's own session directly is the seam _deliver() exists for."""
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json))
        return _FakeResponse(ok=True)

    monkeypatch.setattr("app.webhooks.service.httpx.post", fake_post)

    organizer = _user(session, "wh-deliver-org@example.com", Role.organizer)
    event = _event(session, "wh-deliver", organizer)
    webhook = WebhookSubscription(event_id=event.id, url="https://example.com/hook", created_by_id=organizer.id)
    session.add(webhook)
    session.commit()

    _run(session, event.id, "test.topic", detail="hello")

    assert len(calls) == 1
    url, payload = calls[0]
    assert url == "https://example.com/hook"
    assert payload["record"]["topic"] == "test.topic"
    assert verify_record(payload["record"], payload["signature"], payload["public_key"])

    # Unit-test the status-recording half directly, in-transaction.
    _deliver(webhook.url, webhook.id, payload, session=session)
    session.refresh(webhook)
    assert webhook.last_status == "delivered"


def test_an_unreachable_webhook_does_not_raise_and_records_failed(session):
    organizer = _user(session, "wh-fail-org@example.com", Role.organizer)
    event = _event(session, "wh-fail", organizer)
    webhook = WebhookSubscription(event_id=event.id, url="http://127.0.0.1:1/unreachable", created_by_id=organizer.id)
    session.add(webhook)
    session.commit()

    # A real, short-timeout connection attempt to a closed local port -- must
    # not raise even though it fails, and must record the failure.
    _deliver(webhook.url, webhook.id, {"record": {}, "signature": "", "public_key": "", "algorithm": "ed25519"}, session=session)

    session.refresh(webhook)
    assert webhook.last_status == "failed"


def test_deleting_a_webhook_stops_further_deliveries(client, session, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.webhooks.service.httpx.post",
        lambda url, json, timeout: (calls.append(url), _FakeResponse(ok=True))[1],
    )

    organizer = _login_as(client, session, "wh-stop-org@example.com", Role.organizer)
    event = _event(session, "wh-stop", organizer)
    created = client.post(f"/api/events/{event.id}/webhooks", json={"url": "https://example.com/hook"}).json()
    client.delete(f"/api/events/{event.id}/webhooks/{created['id']}")

    _run(session, event.id, "test.topic")

    assert calls == []
