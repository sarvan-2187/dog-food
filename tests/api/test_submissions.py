from datetime import timedelta

from app.auth.models import Role, User
from app.events.models import Event
from app.timeutil import utcnow


def _setup_event(session, slug: str, *, past: bool = False) -> Event:
    organizer = User(email=f"{slug}-owner@example.com", name="Owner", role=Role.organizer, password_hash="x")
    session.add(organizer)
    session.commit()
    session.refresh(organizer)
    if past:
        start = utcnow() - timedelta(days=5)
        end = utcnow() - timedelta(days=1)
    else:
        start = utcnow() + timedelta(days=1)
        end = utcnow() + timedelta(days=3)
    event = Event(slug=slug, name="Sub Event", start_at=start, end_at=end, created_by_id=organizer.id)
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


def _create_team(client, event_id: int, name: str = "Draft Team") -> int:
    r = client.post(f"/api/events/{event_id}/teams", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_autosave_patch_creates_and_updates_draft(client, session):
    event = _setup_event(session, "sub-event-draft")
    _register(client, "drafter@example.com")
    team_id = _create_team(client, event.id)

    r = client.patch(f"/api/teams/{team_id}/submission", json={"title": "First idea"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "draft"

    r = client.patch(f"/api/teams/{team_id}/submission", json={"description": "More detail."})
    assert r.status_code == 200
    assert r.json()["title"] == "First idea"
    assert r.json()["description"] == "More detail."


def test_deadline_enforced_on_write(client, session):
    # Team formation itself is deadline-gated too, so the team must be created
    # while the event is still open; the deadline is then moved into the past
    # to isolate what this test actually checks: the submission PATCH path.
    event = _setup_event(session, "sub-event-past")
    _register(client, "late@example.com")
    team_id = _create_team(client, event.id, name="Late Team")

    event.end_at = utcnow() - timedelta(days=1)
    session.add(event)
    session.commit()

    r = client.patch(f"/api/teams/{team_id}/submission", json={"title": "Too late"})
    assert r.status_code == 400


def test_submit_requires_title_and_description(client, session):
    event = _setup_event(session, "sub-event-incomplete")
    _register(client, "incomplete@example.com")
    team_id = _create_team(client, event.id, name="Incomplete Team")

    r = client.post(f"/api/teams/{team_id}/submission/submit")
    assert r.status_code == 400

    client.patch(f"/api/teams/{team_id}/submission", json={"title": "T", "description": "D"})
    r = client.post(f"/api/teams/{team_id}/submission/submit")
    assert r.status_code == 200
    assert r.json()["status"] == "submitted"


def test_gallery_shows_only_submitted(client, session):
    event = _setup_event(session, "sub-event-gallery")
    _register(client, "galleryuser@example.com")
    team_id = _create_team(client, event.id, name="Gallery Team")
    client.patch(f"/api/teams/{team_id}/submission", json={"title": "Hidden Draft", "description": "Not yet"})

    r = client.get(f"/api/gallery?event_id={event.id}")
    assert r.json() == []

    client.post(f"/api/teams/{team_id}/submission/submit")
    r = client.get(f"/api/gallery?event_id={event.id}")
    assert "Hidden Draft" in [s["title"] for s in r.json()]


def test_non_member_cannot_patch_submission(client, session):
    event = _setup_event(session, "sub-event-outsider")
    _register(client, "teamowner3@example.com")
    team_id = _create_team(client, event.id, name="Owned Team")

    client.post("/api/auth/logout")
    _register(client, "outsider@example.com")
    r = client.patch(f"/api/teams/{team_id}/submission", json={"title": "Sneaky"})
    assert r.status_code == 403
