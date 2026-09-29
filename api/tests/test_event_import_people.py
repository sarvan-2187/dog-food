"""Event backup round-trips people, the judge panel, assignments and scores
(DOGFOOD T4: "leave as easily as they arrived")."""
from datetime import timedelta

import pytest
from sqlmodel import select

from app.audit.models import AuditLog
from app.auth.models import Role, User
from app.auth.security import hash_password
from app.events.models import Event
from app.judging.models import EventJudge, JudgeAssignment, Rubric
from app.scoring.models import Score
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow

CRITERIA = [
    {"key": "impact", "label": "Impact", "weight": 0.5, "max_score": 10},
    {"key": "execution", "label": "Execution", "weight": 0.5, "max_score": 10},
]


def _user(session, email: str, role: Role) -> User:
    user = User(email=email, name=email.split("@")[0].title(), role=role, password_hash=hash_password("supersecret1"))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _login(client, email: str) -> None:
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": email, "password": "supersecret1"}).status_code == 200


def _judged_event(session, slug: str) -> tuple[Event, dict]:
    """An event with one team of two, one submission, a track judge who scored
    it and an untracked judge who is assigned but hasn't."""
    org = _user(session, f"{slug}-org@example.com", Role.organizer)
    event = Event(
        slug=slug, name="Moving Event", tracks=["Tools"],
        start_at=utcnow() - timedelta(days=3), end_at=utcnow() - timedelta(days=1), created_by_id=org.id,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    session.add(Rubric(event_id=event.id, name="Rubric", criteria=CRITERIA))
    captain = _user(session, f"{slug}-cap@example.com", Role.participant)
    mate = _user(session, f"{slug}-mate@example.com", Role.participant)
    team = Team(event_id=event.id, name="Movers", captain_id=mate.id)
    session.add(team)
    session.commit()
    session.refresh(team)
    session.add(TeamMembership(team_id=team.id, user_id=captain.id))
    session.add(TeamMembership(team_id=team.id, user_id=mate.id))
    sub = Submission(team_id=team.id, event_id=event.id, title="Mover", track="Tools", status=SubmissionStatus.submitted)
    session.add(sub)
    j1 = _user(session, f"{slug}-j1@example.com", Role.judge)
    j2 = _user(session, f"{slug}-j2@example.com", Role.judge)
    session.add(EventJudge(event_id=event.id, user_id=j1.id, track="Tools"))
    session.add(EventJudge(event_id=event.id, user_id=j2.id))
    session.commit()
    a1 = JudgeAssignment(event_id=event.id, submission_id=sub.id, judge_id=j1.id)
    a2 = JudgeAssignment(event_id=event.id, submission_id=sub.id, judge_id=j2.id)
    session.add(a1)
    session.add(a2)
    session.commit()
    session.add(Score(assignment_id=a1.id, submission_id=sub.id, judge_id=j1.id,
                      values={"impact": 8, "execution": 6}, comment="Solid.", raw_total=7.0))
    session.commit()
    return event, {"org": org, "captain": captain, "mate": mate, "j1": j1, "j2": j2}


def _import(client, backup: dict, slug: str, **overrides):
    body = {
        **backup["event"], "slug": slug, "rubrics": backup["rubrics"], "teams": backup["teams"],
        "submissions": backup["submissions"], "judges": backup["judges"],
        "assignments": backup["assignments"], "scores": backup["scores"],
    }
    body.update(overrides)
    return client.post("/api/events/import", json=body)


def test_members_judges_assignments_and_scores_round_trip(client, session):
    event, people = _judged_event(session, "move-out")
    _login(client, "move-out-org@example.com")
    backup = client.get(f"/api/events/{event.id}/export.json").json()
    assert backup["teams"][0]["captain_email"] == "move-out-mate@example.com"
    assert {j["email"]: j["track"] for j in backup["judges"]} == {
        "move-out-j1@example.com": "Tools", "move-out-j2@example.com": None,
    }
    captain_hash = people["captain"].password_hash

    r = _import(client, backup, "move-in")
    assert r.status_code == 201, r.text
    copy = session.exec(select(Event).where(Event.slug == "move-in")).one()

    team = session.exec(select(Team).where(Team.event_id == copy.id)).one()
    members = {m.user_id for m in session.exec(select(TeamMembership).where(TeamMembership.team_id == team.id))}
    assert members == {people["captain"].id, people["mate"].id}, "existing accounts are linked, not duplicated"
    assert team.captain_id == people["mate"].id
    session.refresh(people["captain"])
    assert people["captain"].password_hash == captain_hash and people["captain"].role == Role.participant

    panel = {j.user_id: j.track for j in session.exec(select(EventJudge).where(EventJudge.event_id == copy.id))}
    assert panel == {people["j1"].id: "Tools", people["j2"].id: None}
    assigned = {a.judge_id for a in session.exec(select(JudgeAssignment).where(JudgeAssignment.event_id == copy.id))}
    assert assigned == {people["j1"].id, people["j2"].id}
    sub = session.exec(select(Submission).where(Submission.event_id == copy.id)).one()
    (score,) = session.exec(select(Score).where(Score.submission_id == sub.id)).all()
    assert (score.judge_id, score.values, score.comment, score.raw_total) == (
        people["j1"].id, {"impact": 8, "execution": 6}, "Solid.", pytest.approx(7.0)
    )
    audit = session.exec(select(AuditLog).where(AuditLog.action == "event.imported", AuditLog.entity_id == copy.id)).one()
    assert audit.detail["scores"] == 1 and audit.detail["judges"] == 2 and audit.detail["created_accounts"] == 0


def test_an_unknown_member_gets_a_participant_account_nobody_can_log_into(client, session):
    event, _ = _judged_event(session, "newcomer")
    _login(client, "newcomer-org@example.com")
    backup = client.get(f"/api/events/{event.id}/export.json").json()
    backup["teams"][0]["members"].append({"email": "Brand.New@example.com", "name": "Brand New"})

    assert _import(client, backup, "newcomer-copy").status_code == 201
    created = session.exec(select(User).where(User.email == "Brand.New@example.com")).one()
    assert created.role == Role.participant and created.name == "Brand New"
    client.post("/api/auth/logout")
    for guess in ("", "supersecret1", "Brand New"):
        assert client.post("/api/auth/login", json={"email": "Brand.New@example.com", "password": guess or "x"}).status_code != 200
    assert session.exec(
        select(AuditLog).where(AuditLog.action == "user.created_by_import", AuditLog.entity_id == created.id)
    ).first() is not None


def test_an_unmatched_judge_refuses_the_whole_import(client, session):
    event, _ = _judged_event(session, "no-judge")
    _login(client, "no-judge-org@example.com")
    backup = client.get(f"/api/events/{event.id}/export.json").json()
    for part in ("judges", "assignments", "scores"):
        for row in backup[part]:
            key = "email" if part == "judges" else "judge_email"
            if row[key] == "no-judge-j1@example.com":
                row[key] = "stranger@example.com"

    r = _import(client, backup, "no-judge-copy")
    assert r.status_code == 422
    assert "stranger@example.com" in r.json()["detail"] and "Nothing was imported" in r.json()["detail"]
    assert session.exec(select(Event).where(Event.slug == "no-judge-copy")).first() is None


def test_a_participant_account_is_never_promoted_to_judge_by_import(client, session):
    event, people = _judged_event(session, "promote")
    _login(client, "promote-org@example.com")
    backup = client.get(f"/api/events/{event.id}/export.json").json()
    backup["judges"].append({"email": people["captain"].email, "name": "", "track": None})
    r = _import(client, backup, "promote-copy")
    assert r.status_code == 422 and "has no judge account here" in r.json()["detail"]
    session.refresh(people["captain"])
    assert people["captain"].role == Role.participant


def test_a_score_that_doesnt_match_the_rubric_refuses_the_whole_import(client, session):
    event, _ = _judged_event(session, "bad-score")
    _login(client, "bad-score-org@example.com")
    backup = client.get(f"/api/events/{event.id}/export.json").json()
    backup["scores"][0]["values"] = {"impact": 8, "polish": 6}

    r = _import(client, backup, "bad-score-copy")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "missing execution" in detail and "polish" in detail
    assert session.exec(select(Event).where(Event.slug == "bad-score-copy")).first() is None

    backup["scores"][0]["values"] = {"impact": 11, "execution": 6}
    r = _import(client, backup, "bad-score-copy")
    assert r.status_code == 422 and "outside 0 to 10" in r.json()["detail"]


def test_a_backup_without_people_still_imports_and_only_organizers_may_import(client, session):
    event, _ = _judged_event(session, "old-backup")
    _login(client, "old-backup-org@example.com")
    backup = client.get(f"/api/events/{event.id}/export.json").json()
    old = {**backup["event"], "slug": "old-backup-copy", "rubrics": backup["rubrics"],
           "teams": [{"name": t["name"]} for t in backup["teams"]], "submissions": backup["submissions"]}
    assert client.post("/api/events/import", json=old).status_code == 201

    _login(client, "old-backup-j1@example.com")
    assert _import(client, backup, "old-backup-by-judge").status_code == 403
