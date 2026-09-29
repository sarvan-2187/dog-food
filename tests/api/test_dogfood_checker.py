"""The DOGFOOD acceptance checker's contract, run in-process.

run.py never logs in: it attaches a fixed Cookie header per role. These tests
send exactly that header, so a regression shows up here before the report.
"""
from pathlib import Path

import pytest
from sqlmodel import select

from app.audit.models import AuditLog
from app.auth import deps
from app.auth.models import Role, User
from app.events.models import Event
from app.judging.models import JudgeAssignment
from app.scoring.models import Score
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow

FIXTURE = next(
    (p for p in (Path("/app/fixtures/dogfood.json"), Path(__file__).resolve().parents[2] / "fixtures.json") if p.exists()),
    None,
)


def _as(token: str) -> dict:
    return {"Cookie": f"session={token}"}


@pytest.fixture()
def people(session, monkeypatch):
    users = {}
    for key, role in [("org", Role.organizer), ("judge_a", Role.judge), ("judge_b", Role.judge), ("prt", Role.participant)]:
        users[key] = User(email=f"chk-{key}@example.com", name=key, role=role, password_hash="x")
        session.add(users[key])
    session.commit()
    monkeypatch.setattr(deps, "DEMO_SESSION_TOKENS", {f"tok-{k}": u.email for k, u in users.items()})

    event = Event(slug="chk-event", name="Chk", start_at=utcnow(), end_at=utcnow(), created_by_id=users["org"].id)
    session.add(event)
    session.commit()
    team = Team(event_id=event.id, name="Chk Team")
    session.add(team)
    session.commit()
    sub = Submission(team_id=team.id, event_id=event.id, title="Chk", status=SubmissionStatus.submitted)
    session.add(sub)
    session.commit()
    assignment = JudgeAssignment(event_id=event.id, submission_id=sub.id, judge_id=users["judge_a"].id)
    session.add(assignment)
    session.commit()
    session.add(Score(assignment_id=assignment.id, submission_id=sub.id, judge_id=users["judge_a"].id,
                      values={"impact": 7}, raw_total=7.0))
    session.commit()
    return users


def test_judge_reads_own_scores(client, people):
    r = client.get("/api/judges/me/scores", headers=_as("tok-judge_a"))
    assert r.status_code == 200 and len(r.json()) == 1


def test_judge_cannot_read_peer_scores_and_the_attempt_is_audited(client, session, people):
    r = client.get(f"/api/judges/{people['judge_a'].id}/scores", headers=_as("tok-judge_b"))
    assert r.status_code == 403
    entry = session.exec(select(AuditLog).where(AuditLog.action == "score.peer_read_refused")).first()
    assert entry is not None and entry.actor_id == people["judge_b"].id and entry.entity_id == people["judge_a"].id


def test_participant_and_anonymous_are_refused(client, people):
    assert client.get("/api/judges/me/scores", headers=_as("tok-prt")).status_code == 403
    assert client.get("/api/judges/me/scores").status_code == 401


def test_organizer_may_read_any_judge(client, people):
    r = client.get(f"/api/judges/{people['judge_a'].id}/scores", headers=_as("tok-org"))
    assert r.status_code == 200 and len(r.json()) == 1


def test_demo_token_for_deactivated_account_is_dead(client, session, people):
    people["judge_a"].is_active = False
    session.add(people["judge_a"])
    session.commit()
    assert client.get("/api/judges/me/scores", headers=_as("tok-judge_a")).status_code == 401


@pytest.mark.skipif(FIXTURE is None, reason="official fixtures.json not present")
def test_official_fixtures_load_closed_with_duplicate_folded(client, session, monkeypatch):
    from app.seed import DOGFOOD_EVENT_SLUG, _seed_dogfood

    organizer = User(email="chk-owner@example.com", name="Owner", role=Role.organizer, password_hash="x")
    session.add(organizer)
    session.commit()
    _seed_dogfood(session, FIXTURE)
    _seed_dogfood(session, FIXTURE)  # idempotent: the second run adds nothing
    session.commit()

    event = session.exec(select(Event).where(Event.slug == DOGFOOD_EVENT_SLUG)).one()
    assert event.end_at < utcnow()
    subs = session.exec(select(Submission).where(Submission.event_id == event.id)).all()
    assert len(subs) == 40  # 41 fixture projects, one of them the duplicate
    assert "Glass Signal" in client.get("/api/gallery").text

    # The checker's closed-event probe: a real team member, a past deadline.
    priya = session.exec(select(User).where(User.email == "priya1@example.org")).one()
    team_id = session.exec(select(TeamMembership.team_id).where(TeamMembership.user_id == priya.id)).one()
    monkeypatch.setattr(deps, "DEMO_SESSION_TOKENS", {"tok-p": priya.email})
    r = client.post(f"/api/teams/{team_id}/submission/submit", json={"title": "late"}, headers=_as("tok-p"))
    assert 400 <= r.status_code < 500
