"""One test per defect found in the Phase 0/1 audit.

Each test names the bug it pins down, so a regression fails with an obvious
cause rather than as a mystery elsewhere in the suite.
"""
from datetime import timedelta

from sqlmodel import select

from app.auth.models import Role, User
from app.events.models import Event
from app.timeutil import utcnow


def _organizer(session, email: str) -> User:
    user = User(email=email, name="Org", role=Role.organizer, password_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _event(session, slug: str) -> Event:
    owner = _organizer(session, f"{slug}-owner@example.com")
    event = Event(
        slug=slug,
        name="Regression Event",
        start_at=utcnow() + timedelta(days=1),
        end_at=utcnow() + timedelta(days=3),
        created_by_id=owner.id,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def _promote(client, session, email: str) -> None:
    """Register through the API (so the session cookie is set) then promote, since
    public sign-up is always a participant by design."""
    client.post("/api/auth/register", json={"email": email, "password": "supersecret1", "name": "Promoted"})
    user = session.exec(select(User).where(User.email == email)).first()
    user.role = Role.organizer
    session.add(user)
    session.commit()


def _register(client, email: str) -> None:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "supersecret1", "name": email.split("@")[0]},
    )
    assert r.status_code == 201, r.text


# --- datetimes carry an offset, so the browser cannot misread them as local ---

def test_event_datetimes_serialize_with_utc_offset(client, session):
    """A naive `2026-09-21T18:00:00` is parsed as *local* time by `new Date()`,
    drifting the deadline the participant sees from the one the API enforces."""
    event = _event(session, "tz-event")
    body = client.get(f"/api/events/{event.slug}").json()
    for field in ("start_at", "end_at", "created_at"):
        value = body[field]
        assert value.endswith("Z") or "+" in value[10:], f"{field} has no offset: {value}"


def test_naive_datetime_from_client_is_read_as_utc(client, session):
    _promote(client, session, "naive@example.com")

    start = (utcnow() + timedelta(days=1)).replace(tzinfo=None).isoformat()
    end = (utcnow() + timedelta(days=2)).replace(tzinfo=None).isoformat()
    r = client.post(
        "/api/events",
        json={"name": "Naive Dates", "slug": "naive-dates", "start_at": start, "end_at": end},
    )
    assert r.status_code == 201, r.text
    assert r.json()["start_at"].endswith("Z") or "+" in r.json()["start_at"][10:]


# --- an explicitly-null autosave field is a no-op, not a 500 ---

def test_patch_submission_with_null_field_does_not_500(client, session):
    event = _event(session, "null-patch")
    _register(client, "nullpatch@example.com")
    team_id = client.post(f"/api/events/{event.id}/teams", json={"name": "Null Team"}).json()["id"]

    client.patch(f"/api/teams/{team_id}/submission", json={"title": "Kept"})
    r = client.patch(f"/api/teams/{team_id}/submission", json={"title": None})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Kept", "an explicit null must not overwrite the stored value"


def test_patch_submission_rejects_overlong_title(client, session):
    event = _event(session, "long-title")
    _register(client, "longtitle@example.com")
    team_id = client.post(f"/api/events/{event.id}/teams", json={"name": "Long Team"}).json()["id"]
    r = client.patch(f"/api/teams/{team_id}/submission", json={"title": "x" * 121})
    assert r.status_code == 422


# --- unknown API paths 404 as JSON instead of returning the SPA shell ---

def test_unknown_api_path_returns_404_not_the_spa(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404, f"got {r.status_code} {r.headers.get('content-type')}"
    assert "text/html" not in (r.headers.get("content-type") or "")


# --- deleting an event with dependents is refused, not a foreign-key 500 ---

def test_delete_event_with_teams_is_refused_clearly(client, session):
    event = _event(session, "delete-guard")
    _register(client, "deleteguard@example.com")
    client.post(f"/api/events/{event.id}/teams", json={"name": "Blocking Team"})

    client.post("/api/auth/logout")
    _promote(client, session, "del-org@example.com")

    r = client.delete(f"/api/events/{event.id}")
    assert r.status_code == 409, r.text
    assert "team" in r.json()["detail"].lower()


def test_delete_event_without_dependents_succeeds(client, session):
    event = _event(session, "delete-ok")
    _promote(client, session, "del-ok@example.com")
    assert client.delete(f"/api/events/{event.id}").status_code == 204


# --- PATCH cannot push an event into a state POST would have rejected ---

def test_patch_event_cannot_invert_dates(client, session):
    event = _event(session, "patch-dates")
    _promote(client, session, "patch-org@example.com")

    earlier = (event.start_at - timedelta(days=1)).isoformat()
    r = client.patch(f"/api/events/{event.id}", json={"end_at": earlier})
    assert r.status_code == 422, r.text


# --- a literal % or _ in the search box matches itself, not everything ---

def test_gallery_search_escapes_like_wildcards(client, session):
    event = _event(session, "wildcard")
    _register(client, "wildcard@example.com")
    team_id = client.post(f"/api/events/{event.id}/teams", json={"name": "Wildcard Team"}).json()["id"]
    client.patch(
        f"/api/teams/{team_id}/submission",
        json={"title": "Plain title", "description": "No special characters here."},
    )
    client.post(f"/api/teams/{team_id}/submission/submit")

    assert len(client.get(f"/api/gallery?event_id={event.id}").json()) == 1
    for wildcard in ("%", "_", "%%"):
        hits = client.get(f"/api/gallery?event_id={event.id}", params={"q": wildcard}).json()
        assert hits == [], f"q={wildcard!r} matched {len(hits)} row(s); wildcards must be escaped"
