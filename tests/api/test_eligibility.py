"""Eligibility review: an organizer disqualifies or reinstates a submitted entry."""
from datetime import timedelta

from sqlmodel import select

from app.audit.models import AuditLog
from app.auth.models import Role, User
from app.events.models import Event
from app.judging.models import JudgeAssignment
from app.scoring.models import Score
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team
from app.timeutil import utcnow


def _user(session, email: str, role: Role) -> User:
    user = User(email=email, name=email.split("@")[0], role=role, password_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _login_as(client, session, email: str, role: Role) -> User:
    client.post("/api/auth/register", json={"email": email, "password": "supersecret1", "name": "Tester"})
    user = session.exec(select(User).where(User.email == email)).first()
    user.role = role
    session.add(user)
    session.commit()
    return user


def _setup(session):
    """A closed event, two submitted entries, and two judges who each scored
    entry A and have entry B assigned but unscored."""
    owner = _user(session, "elig-owner@example.com", Role.organizer)
    event = Event(
        slug="elig",
        name="Eligibility",
        start_at=utcnow() - timedelta(days=3),
        end_at=utcnow() - timedelta(hours=1),
        created_by_id=owner.id,
        voting_enabled=True,
    )
    session.add(event)
    session.commit()
    subs = []
    for name in ("A", "B"):
        team = Team(event_id=event.id, name=f"Team {name}")
        session.add(team)
        session.commit()
        sub = Submission(
            team_id=team.id, event_id=event.id, title=f"Entry {name}", description="d", status=SubmissionStatus.submitted
        )
        session.add(sub)
        session.commit()
        subs.append(sub)
    a, b = subs
    for i, raw in enumerate((6.0, 8.0)):
        judge = _user(session, f"elig-judge{i}@example.com", Role.judge)
        for sub in subs:
            assignment = JudgeAssignment(event_id=event.id, submission_id=sub.id, judge_id=judge.id)
            session.add(assignment)
            session.commit()
            if sub is a:
                session.add(Score(assignment_id=assignment.id, submission_id=a.id, judge_id=judge.id, raw_total=raw))
                session.commit()
    return event, a, b


def test_disqualified_entry_leaves_gallery_voting_and_standings(client, session):
    event, a, b = _setup(session)
    _login_as(client, session, "elig-org@example.com", Role.organizer)
    assert {r["submission_id"] for r in client.get(f"/api/events/{event.id}/results").json()} == {a.id}

    r = client.post(f"/api/submissions/{a.id}/eligibility", json={"eligible": False, "reason": "Pre-existing code"})
    assert r.status_code == 200, r.text
    assert r.json()["disqualified_reason"] == "Pre-existing code"

    assert a.id not in {g["id"] for g in client.get(f"/api/gallery?event_id={event.id}").json()}
    assert client.get(f"/api/submissions/{a.id}").status_code == 404
    assert client.post(f"/api/submissions/{a.id}/vote").status_code == 404
    assert client.get(f"/api/events/{event.id}/results").json() == []
    # Still listed for the organizer, disqualified first, so it can be reinstated.
    rows = client.get(f"/api/events/{event.id}/eligibility").json()
    assert [row["submission_id"] for row in rows] == [a.id, b.id]
    assert session.exec(select(AuditLog).where(AuditLog.action == "submission.disqualified")).first()


def test_disqualifying_releases_unscored_work_and_reinstating_restores_scores(client, session):
    event, a, b = _setup(session)
    _login_as(client, session, "elig-org2@example.com", Role.organizer)

    client.post(f"/api/submissions/{b.id}/eligibility", json={"eligible": False, "reason": "Late"})
    assert session.exec(select(JudgeAssignment).where(JudgeAssignment.submission_id == b.id)).all() == []

    client.post(f"/api/submissions/{a.id}/eligibility", json={"eligible": False, "reason": "Copied"})
    # Scored assignments and their scores survive a disqualification...
    assert len(session.exec(select(Score).where(Score.submission_id == a.id)).all()) == 2
    r = client.post(f"/api/submissions/{a.id}/eligibility", json={"eligible": True})
    assert r.status_code == 200 and r.json()["disqualified_at"] is None
    # ...so reinstating puts the entry straight back in the standings.
    assert [row["submission_id"] for row in client.get(f"/api/events/{event.id}/results").json()] == [a.id]


def test_disqualifying_needs_a_reason_and_an_organizer(client, session):
    event, a, _ = _setup(session)
    _login_as(client, session, "elig-part@example.com", Role.participant)
    assert client.post(f"/api/submissions/{a.id}/eligibility", json={"eligible": False, "reason": "x"}).status_code == 403
    assert client.get(f"/api/events/{event.id}/eligibility").status_code == 403

    _login_as(client, session, "elig-org3@example.com", Role.organizer)
    assert client.post(f"/api/submissions/{a.id}/eligibility", json={"eligible": False, "reason": "  "}).status_code == 422
