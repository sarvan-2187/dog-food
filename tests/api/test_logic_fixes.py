"""Regression tests for the logic errors fixed in the code review (task 3)."""
from datetime import timedelta

from sqlmodel import select

from app.auth.models import Role, User
from app.events.models import Event
from app.judging.models import EventJudge, Rubric
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow
from app.webhooks.models import WebhookSubscription

PASSWORD = "supersecret1"


def _register(client, email: str, name: str = "Some One"):
    return client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "name": name})


def _organizer(client, session, email: str = "logic-org@example.com") -> User:
    assert _register(client, email).status_code == 201
    user = session.exec(select(User).where(User.email == email)).first()
    user.role = Role.organizer
    session.add(user)
    session.commit()
    return user


def _event(session, owner: User, slug: str = "logic-event", **kw) -> Event:
    event = Event(
        slug=slug,
        name="Logic Event",
        start_at=utcnow() - timedelta(days=1),
        end_at=utcnow() + timedelta(days=2),
        created_by_id=owner.id,
        **kw,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


# --- emails are one account regardless of case ------------------------------

def test_register_refuses_same_email_in_other_case(client):
    assert _register(client, "Case.Person@Example.com").status_code == 201
    client.post("/api/auth/logout")
    r = _register(client, "case.person@example.com")
    assert r.status_code == 409


def test_login_ignores_email_case(client):
    assert _register(client, "Mixed.Case@example.com").status_code == 201
    client.post("/api/auth/logout")
    for typed in ("mixed.case@example.com", "MIXED.CASE@EXAMPLE.COM", "  Mixed.Case@example.com"):
        r = client.post("/api/auth/login", json={"email": typed.strip(), "password": PASSWORD})
        assert r.status_code == 200, (typed, r.text)


def test_new_accounts_store_lowercase_email(client):
    r = _register(client, "UPPER@example.com")
    assert r.json()["email"] == "upper@example.com"


def test_login_still_finds_legacy_mixed_case_account(client, session):
    from app.auth.security import hash_password

    session.add(User(email="Legacy.User@example.com", name="Legacy", role=Role.participant,
                     password_hash=hash_password(PASSWORD)))
    session.commit()
    r = client.post("/api/auth/login", json={"email": "legacy.user@example.com", "password": PASSWORD})
    assert r.status_code == 200


# --- deleting a configured-but-empty event ----------------------------------

def test_event_with_setup_but_no_entries_can_be_deleted(client, session):
    org = _organizer(client, session)
    event = _event(session, org, "delete-me")
    session.add(Rubric(event_id=event.id, name="Main", criteria=[
        {"key": "q", "label": "Quality", "weight": 1.0, "max_score": 10}]))
    judge = User(email="delete-judge@example.com", name="Judge", role=Role.judge, password_hash="x")
    session.add(judge)
    session.commit()
    session.add(EventJudge(event_id=event.id, user_id=judge.id))
    session.add(WebhookSubscription(event_id=event.id, url="https://hooks.example.com/x", created_by_id=org.id))
    session.commit()

    r = client.delete(f"/api/events/{event.id}")
    assert r.status_code == 204, r.text
    assert session.get(Event, event.id) is None
    assert not session.exec(select(Rubric).where(Rubric.event_id == event.id)).all()


def test_event_with_teams_still_cannot_be_deleted(client, session):
    org = _organizer(client, session)
    event = _event(session, org, "keep-me")
    session.add(Team(event_id=event.id, name="Busy"))
    session.commit()
    assert client.delete(f"/api/events/{event.id}").status_code == 409


# --- results/exports for an event that doesn't exist -----------------------

def test_results_and_exports_404_for_unknown_event(client, session):
    _organizer(client, session)
    for path in ("results", "export/scores.csv", "export/results.csv", "export/assignments.csv",
                 "export/submissions.csv", "export/users.csv"):
        r = client.get(f"/api/events/987654/{path}")
        assert r.status_code == 404, path


# --- teams ------------------------------------------------------------------

def test_create_team_is_one_transaction(client, session):
    org = User(email="team-owner@example.com", name="Owner", role=Role.organizer, password_hash="x")
    session.add(org)
    session.commit()
    event = _event(session, org, "team-atomic")
    assert _register(client, "captain@example.com").status_code == 201
    r = client.post(f"/api/events/{event.id}/teams", json={"name": "First Team"})
    assert r.status_code == 201
    r = client.post(f"/api/events/{event.id}/teams", json={"name": "Second Team"})
    assert r.status_code == 409
    teams = session.exec(select(Team).where(Team.event_id == event.id)).all()
    assert [t.name for t in teams] == ["First Team"]
    for team in teams:
        assert session.exec(select(TeamMembership).where(TeamMembership.team_id == team.id)).first()


# --- gallery ----------------------------------------------------------------

def test_gallery_search_length_is_bounded(client):
    assert client.get("/api/gallery", params={"q": "x" * 201}).status_code == 422
    assert client.get("/api/gallery", params={"q": "x" * 200}).status_code == 200

