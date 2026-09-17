from datetime import datetime, timedelta

from app.auth.models import Role, User
from app.events.models import Event


def _setup_event(session, name: str = "team-event") -> Event:
    organizer = User(email=f"{name}-owner@example.com", name="Owner", role=Role.organizer, password_hash="x")
    session.add(organizer)
    session.commit()
    session.refresh(organizer)
    event = Event(
        slug=name,
        name="Team Event",
        start_at=datetime.utcnow() + timedelta(days=1),
        end_at=datetime.utcnow() + timedelta(days=3),
        created_by_id=organizer.id,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def _register(client, email: str) -> None:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "supersecret1", "name": email.split("@")[0]},
    )
    assert r.status_code == 201, r.text


def test_create_team_and_invite_join(client, session):
    event = _setup_event(session)
    _register(client, "creator@example.com")
    r = client.post(f"/api/events/{event.id}/teams", json={"name": "Team Rocket"})
    assert r.status_code == 201, r.text
    team = r.json()
    assert team["members"][0]["email"] == "creator@example.com"

    client.post("/api/auth/logout")
    _register(client, "joiner@example.com")
    r = client.post("/api/teams/join", json={"invite_code": team["invite_code"]})
    assert r.status_code == 200, r.text
    assert len(r.json()["members"]) == 2


def test_join_with_bad_code_404(client):
    _register(client, "lonely@example.com")
    r = client.post("/api/teams/join", json={"invite_code": "not-a-real-code"})
    assert r.status_code == 404


def test_join_twice_conflict(client, session):
    event = _setup_event(session, "team-event-2")
    _register(client, "solo@example.com")
    r = client.post(f"/api/events/{event.id}/teams", json={"name": "Solo Team"})
    invite_code = r.json()["invite_code"]
    r = client.post("/api/teams/join", json={"invite_code": invite_code})
    assert r.status_code == 409


def test_non_member_cannot_view_team(client, session):
    event = _setup_event(session, "team-event-3")
    _register(client, "owner2@example.com")
    r = client.post(f"/api/events/{event.id}/teams", json={"name": "Private Team"})
    team_id = r.json()["id"]

    client.post("/api/auth/logout")
    _register(client, "stranger@example.com")
    r = client.get(f"/api/teams/{team_id}")
    assert r.status_code == 403
