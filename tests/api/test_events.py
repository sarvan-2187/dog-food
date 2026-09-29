from datetime import timedelta

from sqlmodel import select

from app.auth.models import Role, User
from app.timeutil import utcnow


def _future_event_payload(slug: str = "test-event") -> dict:
    start = utcnow() + timedelta(days=1)
    end = start + timedelta(days=2)
    return {
        "name": "Test Event",
        "slug": slug,
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
        "tracks": ["General"],
    }


def _make_organizer(client, session, email: str = "org1@example.com") -> User:
    client.post("/api/auth/register", json={"email": email, "password": "supersecret1", "name": "Org"})
    user = session.exec(select(User).where(User.email == email)).first()
    user.role = Role.organizer
    session.add(user)
    session.commit()
    return user


def test_participant_cannot_create_event(client):
    r = client.post("/api/auth/register", json={"email": "p1@example.com", "password": "supersecret1", "name": "Participant"})
    assert r.status_code == 201, r.text
    r = client.post("/api/events", json=_future_event_payload())
    assert r.status_code == 403


def test_organizer_can_create_and_list_event(client, session):
    _make_organizer(client, session)
    r = client.post("/api/events", json=_future_event_payload("organizer-event"))
    assert r.status_code == 201, r.text

    r = client.get("/api/events")
    assert r.status_code == 200
    assert "organizer-event" in [e["slug"] for e in r.json()]


def test_duplicate_slug_rejected(client, session):
    _make_organizer(client, session)
    client.post("/api/events", json=_future_event_payload("dup-slug"))
    r = client.post("/api/events", json=_future_event_payload("dup-slug"))
    assert r.status_code == 409


def test_invalid_slug_rejected(client, session):
    _make_organizer(client, session)
    r = client.post("/api/events", json=_future_event_payload("Not A Slug!"))
    assert r.status_code == 422


def test_end_before_start_rejected(client, session):
    _make_organizer(client, session)
    payload = _future_event_payload("bad-dates")
    payload["end_at"] = payload["start_at"]
    r = client.post("/api/events", json=payload)
    assert r.status_code == 422


def test_get_unknown_event_404(client):
    assert client.get("/api/events/does-not-exist").status_code == 404
