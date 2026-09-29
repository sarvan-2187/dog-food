"""Soft judging deadline: shown to judges and organizers, late scores flagged, never refused."""
from datetime import timedelta

from sqlmodel import select

from app.audit.models import AuditLog
from app.auth.models import Role, User
from app.events.models import Event
from app.judging.models import EventJudge, JudgeAssignment
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team
from app.timeutil import utcnow

CRITERIA = [
    {"key": "impact", "label": "Impact", "weight": 0.5, "max_score": 10},
    {"key": "execution", "label": "Execution", "weight": 0.5, "max_score": 10},
]


def _login_as(client, session, email: str, role: Role) -> User:
    client.post("/api/auth/logout")
    if not session.exec(select(User).where(User.email == email)).first():
        client.post("/api/auth/register", json={"email": email, "password": "supersecret1", "name": "Tester"})
    user = session.exec(select(User).where(User.email == email)).first()
    user.role = role
    session.add(user)
    session.commit()
    client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    return user


def _closed_event(session) -> Event:
    owner = User(email="dl-owner@example.com", name="Owner", role=Role.organizer, password_hash="x")
    session.add(owner)
    session.commit()
    event = Event(
        slug="deadline",
        name="Deadline",
        start_at=utcnow() - timedelta(days=3),
        end_at=utcnow() - timedelta(hours=2),
        created_by_id=owner.id,
    )
    session.add(event)
    session.commit()
    return event


def test_deadline_must_follow_submissions_close_and_can_be_cleared(client, session):
    event = _closed_event(session)
    _login_as(client, session, "dl-org@example.com", Role.organizer)

    too_early = (event.end_at - timedelta(minutes=1)).isoformat()
    assert client.patch(f"/api/events/{event.id}", json={"judging_deadline": too_early}).status_code == 422

    due = (utcnow() + timedelta(days=7)).isoformat()
    r = client.patch(f"/api/events/{event.id}", json={"judging_deadline": due})
    assert r.status_code == 200 and r.json()["judging_deadline"] is not None

    r = client.patch(f"/api/events/{event.id}", json={"judging_deadline": None})
    assert r.status_code == 200 and r.json()["judging_deadline"] is None


def test_judges_see_the_due_date_and_a_late_score_saves_but_is_flagged(client, session):
    event = _closed_event(session)
    _login_as(client, session, "dl-org2@example.com", Role.organizer)
    assert client.post(f"/api/events/{event.id}/rubrics", json={"name": "Test Rubric", "criteria": CRITERIA}).status_code == 201
    # Already past: after submissions closed, before now.
    past = (utcnow() - timedelta(hours=1)).isoformat()
    assert client.patch(f"/api/events/{event.id}", json={"judging_deadline": past}).status_code == 200
    assert client.get(f"/api/events/{event.id}/judges").json()["judging_deadline"] is not None

    team = Team(event_id=event.id, name="T")
    session.add(team)
    session.commit()
    sub = Submission(team_id=team.id, event_id=event.id, title="S", description="d", status=SubmissionStatus.submitted)
    session.add(sub)
    session.commit()
    judge = _login_as(client, session, "dl-judge@example.com", Role.judge)
    session.add(EventJudge(event_id=event.id, user_id=judge.id))
    assignment = JudgeAssignment(event_id=event.id, submission_id=sub.id, judge_id=judge.id)
    session.add(assignment)
    session.commit()

    rows = client.get("/api/judge/assignments").json()["pending"]
    assert rows[0]["due_at"] is not None
    assert client.get("/api/judge/events").json()[0]["judging_deadline"] is not None

    r = client.put(f"/api/assignments/{assignment.id}/score", json={"values": {"impact": 8, "execution": 7}})
    assert r.status_code == 200, r.text
    entry = session.exec(select(AuditLog).where(AuditLog.action == "score.submitted")).first()
    assert entry.detail["late"] is True
