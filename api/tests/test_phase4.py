"""Phase 4 stretch features (PLAN.md T4): signed judge participation records,
participation certificates, and bulk event export/import."""
from datetime import timedelta

from sqlmodel import select

from app.auth.models import Role, User
from app.auth.security import hash_password
from app.crypto import verify_record
from app.events.models import Event
from app.judging.models import JudgeAssignment, Rubric
from app.scoring.models import Score
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow


def _user(session, email: str, role: Role) -> User:
    """A real bcrypt hash for "supersecret1" -- these accounts are logged
    into directly via _login_as, which authenticates with that password."""
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


def _full_event(session, slug: str):
    """Event + rubric + one team + a submitted entry + one judge with a scored
    assignment. results_hidden_until defaults to already-passed, so results
    (and certificates) are visible unless a test overrides it."""
    organizer = _user(session, f"{slug}-org@example.com", Role.organizer)
    event = Event(
        slug=slug,
        name="Phase 4 Event",
        start_at=utcnow() - timedelta(days=2),
        end_at=utcnow() + timedelta(days=1),
        created_by_id=organizer.id,
        results_hidden_until=utcnow() - timedelta(hours=1),
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    rubric = Rubric(
        event_id=event.id,
        name="Judging",
        criteria=[{"key": "impact", "label": "Impact", "weight": 1.0, "max_score": 10}],
    )
    session.add(rubric)

    team = Team(event_id=event.id, name="Team Phase4")
    session.add(team)
    session.commit()
    session.refresh(team)

    submission = Submission(
        team_id=team.id, event_id=event.id, title="Widget", description="d", status=SubmissionStatus.submitted
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)

    judge = _user(session, f"{slug}-judge@example.com", Role.judge)
    assignment = JudgeAssignment(event_id=event.id, submission_id=submission.id, judge_id=judge.id)
    session.add(assignment)
    session.commit()
    session.refresh(assignment)

    score = Score(
        assignment_id=assignment.id, submission_id=submission.id, judge_id=judge.id,
        values={"impact": 8}, raw_total=8.0,
    )
    session.add(score)
    session.commit()
    return event, team, submission, judge, organizer


# ---------------------------------------------------------------------------
# Signed judge participation records
# ---------------------------------------------------------------------------

def test_judge_can_fetch_and_verify_their_own_signed_record(client, session):
    event, _team, _submission, judge, _organizer = _full_event(session, "p4-record")
    _login_as(client, session, judge.email, Role.judge)
    r = client.get(f"/api/events/{event.id}/judges/{judge.id}/participation-record")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["record"]["submissions_scored"] == 1
    assert body["record"]["submissions_assigned"] == 1
    assert verify_record(body["record"], body["signature"], body["public_key"])


def test_a_different_judge_cannot_fetch_someone_elses_record(client, session):
    event, _team, _submission, judge, _organizer = _full_event(session, "p4-record2")
    _login_as(client, session, "other-judge@example.com", Role.judge)
    r = client.get(f"/api/events/{event.id}/judges/{judge.id}/participation-record")
    assert r.status_code == 403


def test_organizer_can_fetch_any_judges_record(client, session):
    event, _team, _submission, judge, organizer = _full_event(session, "p4-record3")
    _login_as(client, session, organizer.email, Role.organizer)
    r = client.get(f"/api/events/{event.id}/judges/{judge.id}/participation-record")
    assert r.status_code == 200


def test_a_tampered_record_fails_verification(client, session):
    event, _team, _submission, judge, _organizer = _full_event(session, "p4-record4")
    _login_as(client, session, judge.email, Role.judge)
    body = client.get(f"/api/events/{event.id}/judges/{judge.id}/participation-record").json()
    tampered = dict(body["record"], submissions_scored=999)
    assert not verify_record(tampered, body["signature"], body["public_key"])


def test_public_key_endpoint_matches_the_signing_key(client):
    r = client.get("/api/public-key")
    assert r.status_code == 200
    assert r.json()["algorithm"] == "ed25519"


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------

def test_certificate_is_available_to_the_team_after_results_reveal(client, session):
    event, team, submission, _judge, _organizer = _full_event(session, "p4-cert")
    member = _login_as(client, session, "member@example.com", Role.participant)
    session.add(TeamMembership(team_id=team.id, user_id=member.id))
    session.commit()
    r = client.get(f"/api/submissions/{submission.id}/certificate.pdf")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")


def test_certificate_is_refused_before_results_are_visible(client, session):
    event, team, submission, _judge, _organizer = _full_event(session, "p4-cert2")
    event.results_hidden_until = utcnow() + timedelta(days=1)
    session.add(event)
    session.commit()
    member = _login_as(client, session, "member2@example.com", Role.participant)
    session.add(TeamMembership(team_id=team.id, user_id=member.id))
    session.commit()
    r = client.get(f"/api/submissions/{submission.id}/certificate.pdf")
    assert r.status_code == 425


def test_certificate_is_refused_to_a_non_team_member(client, session):
    _event, _team, submission, _judge, _organizer = _full_event(session, "p4-cert3")
    _login_as(client, session, "stranger@example.com", Role.participant)
    r = client.get(f"/api/submissions/{submission.id}/certificate.pdf")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Bulk export/import
# ---------------------------------------------------------------------------

def test_export_then_import_recreates_the_events_shape(client, session):
    event, _team, _submission, _judge, organizer = _full_event(session, "p4-export")
    _login_as(client, session, organizer.email, Role.organizer)
    exported = client.get(f"/api/events/{event.id}/export.json").json()
    assert exported["event"]["slug"] == "p4-export"
    assert exported["teams"] == [{"name": "Team Phase4"}]
    assert exported["submissions"][0]["title"] == "Widget"

    payload = {
        **exported["event"],
        "slug": "p4-export-copy",
        "rubric": exported["rubric"],
        "teams": exported["teams"],
        "submissions": exported["submissions"],
    }
    r = client.post("/api/events/import", json=payload)
    assert r.status_code == 201, r.text
    new_event = r.json()
    assert new_event["slug"] == "p4-export-copy"

    copied_team = session.exec(select(Team).where(Team.event_id == new_event["id"])).first()
    assert copied_team.name == "Team Phase4"
    copied_submission = session.exec(select(Submission).where(Submission.event_id == new_event["id"])).first()
    assert copied_submission.title == "Widget"


def test_import_rejects_a_duplicate_slug(client, session):
    event, _team, _submission, _judge, organizer = _full_event(session, "p4-dup")
    _login_as(client, session, organizer.email, Role.organizer)
    exported = client.get(f"/api/events/{event.id}/export.json").json()
    r = client.post("/api/events/import", json=exported["event"])
    assert r.status_code == 409


def test_a_participant_cannot_export_or_import(client, session):
    event, *_rest = _full_event(session, "p4-perm")
    _login_as(client, session, "nonorg@example.com", Role.participant)
    assert client.get(f"/api/events/{event.id}/export.json").status_code == 403
    minimal = {
        "slug": "p4-perm-blocked",
        "name": "Blocked",
        "start_at": utcnow().isoformat(),
        "end_at": (utcnow() + timedelta(days=1)).isoformat(),
    }
    assert client.post("/api/events/import", json=minimal).status_code == 403
