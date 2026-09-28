from datetime import timedelta

from app.auth.models import Role, User
from app.events.models import Event
from app.timeutil import utcnow


def _setup_event(session, name: str = "team-event", max_team_size: int = 4) -> Event:
    organizer = User(email=f"{name}-owner@example.com", name="Owner", role=Role.organizer, password_hash="x")
    session.add(organizer)
    session.commit()
    session.refresh(organizer)
    event = Event(
        slug=name,
        name="Team Event",
        start_at=utcnow() + timedelta(days=1),
        end_at=utcnow() + timedelta(days=3),
        created_by_id=organizer.id,
        max_team_size=max_team_size,
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


# --- team-size cap (PLAN.md Phase 7.2) ------------------------------------

def test_a_full_team_refuses_a_new_join_in_plain_language(client, session):
    # max_team_size=1: the creator alone already fills it, so the very next
    # join attempt must be refused -- the creator counts toward the cap too.
    event = _setup_event(session, "team-cap-full", max_team_size=1)
    _register(client, "cap-creator@example.com")
    r = client.post(f"/api/events/{event.id}/teams", json={"name": "Solo Capped"})
    invite_code = r.json()["invite_code"]

    client.post("/api/auth/logout")
    _register(client, "cap-latecomer@example.com")
    r = client.post("/api/teams/join", json={"invite_code": invite_code})
    assert r.status_code == 409
    assert "full" in r.json()["detail"].lower()
    assert "1" in r.json()["detail"]


def test_joining_up_to_the_cap_succeeds_one_over_it_does_not(client, session):
    event = _setup_event(session, "team-cap-two", max_team_size=2)
    _register(client, "cap2-creator@example.com")
    r = client.post(f"/api/events/{event.id}/teams", json={"name": "Duo"})
    invite_code = r.json()["invite_code"]

    client.post("/api/auth/logout")
    _register(client, "cap2-second@example.com")
    r = client.post("/api/teams/join", json={"invite_code": invite_code})
    assert r.status_code == 200, r.text
    assert len(r.json()["members"]) == 2

    client.post("/api/auth/logout")
    _register(client, "cap2-third@example.com")
    r = client.post("/api/teams/join", json={"invite_code": invite_code})
    assert r.status_code == 409


def test_default_max_team_size_matches_the_hackathons_own_rule(client, session):
    """An event created without specifying a cap behaves exactly as every
    event did before this feature existed -- default 4, per the brief's own
    "Team Size: 1-4 members" rule."""
    event = _setup_event(session, "team-cap-default")
    assert event.max_team_size == 4
