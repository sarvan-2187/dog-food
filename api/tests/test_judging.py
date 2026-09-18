"""Assignment algorithm (pure) and the judging endpoints (PLAN.md Phase 2)."""
from dataclasses import dataclass
from datetime import timedelta

import pytest
from sqlmodel import select

from app.auth.models import Role, User
from app.events.models import Event
from app.judging.assignment import assign_judges, build_conflict_set, coverage_report
from app.judging.models import JudgeAssignment, Rubric
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow


# ---------------------------------------------------------------------------
# The pure algorithm -- no database (PLAN.md section 8: "a pure, testable
# function separate from the endpoint handler")
# ---------------------------------------------------------------------------

@dataclass
class FakeSubmission:
    id: int
    team_id: int
    event_id: int = 1


@dataclass
class FakeJudge:
    id: int


@dataclass
class FakeMembership:
    team_id: int
    user_id: int


def test_judge_is_never_assigned_their_own_teams_submission():
    submissions = [FakeSubmission(1, team_id=10), FakeSubmission(2, team_id=20)]
    judges = [FakeJudge(100), FakeJudge(101), FakeJudge(102)]
    memberships = [FakeMembership(team_id=10, user_id=100)]  # judge 100 is on team 10

    conflicts = build_conflict_set(submissions, memberships)
    assert (100, 1) in conflicts

    assignments = assign_judges(submissions, judges, memberships, k=3)
    assert (100, 1) not in {(a.judge_id, a.submission_id) for a in assignments}
    # ...but judge 100 may still score the other team's submission.
    assert (100, 2) in {(a.judge_id, a.submission_id) for a in assignments}


def test_load_is_balanced_across_judges():
    submissions = [FakeSubmission(i, team_id=i * 10) for i in range(1, 7)]
    judges = [FakeJudge(j) for j in (100, 101, 102)]
    assignments = assign_judges(submissions, judges, [], k=2)

    load: dict[int, int] = {}
    for a in assignments:
        load[a.judge_id] = load.get(a.judge_id, 0) + 1
    assert len(assignments) == 12
    assert max(load.values()) - min(load.values()) <= 1, load


def test_result_is_deterministic_and_ties_break_by_judge_id():
    submissions = [FakeSubmission(1, team_id=10)]
    judges = [FakeJudge(103), FakeJudge(101), FakeJudge(102)]
    first = assign_judges(submissions, judges, [], k=2)
    second = assign_judges(submissions, judges, [], k=2)
    pairs = [(a.submission_id, a.judge_id) for a in first]
    assert pairs == [(a.submission_id, a.judge_id) for a in second]
    # All loads start at 0, so the tie-break is judge id ascending.
    assert pairs == [(1, 101), (1, 102)]


def test_each_submission_gets_exactly_k_judges_when_enough_are_eligible():
    submissions = [FakeSubmission(i, team_id=i * 10) for i in range(1, 4)]
    judges = [FakeJudge(j) for j in range(100, 105)]
    assignments = assign_judges(submissions, judges, [], k=3)
    per_submission: dict[int, int] = {}
    for a in assignments:
        per_submission[a.submission_id] = per_submission.get(a.submission_id, 0) + 1
    assert per_submission == {1: 3, 2: 3, 3: 3}
    assert coverage_report(submissions, assignments, k=3) == {}


def test_shortfall_is_reported_not_papered_over():
    """Two judges and k=3 means every submission is one judge short. That must be
    reported rather than quietly relaxing a conflict."""
    submissions = [FakeSubmission(1, team_id=10)]
    judges = [FakeJudge(100), FakeJudge(101)]
    assignments = assign_judges(submissions, judges, [], k=3)
    assert len(assignments) == 2
    assert coverage_report(submissions, assignments, k=3) == {1: 1}


def test_no_judges_or_zero_k_yields_nothing():
    submissions = [FakeSubmission(1, team_id=10)]
    assert assign_judges(submissions, [], [], k=3) == []
    assert assign_judges(submissions, [FakeJudge(1)], [], k=0) == []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

VALID_CRITERIA = [
    {"key": "impact", "label": "Impact", "weight": 0.5, "max_score": 10},
    {"key": "execution", "label": "Execution", "weight": 0.5, "max_score": 10},
]


def _user(session, email: str, role: Role) -> User:
    user = User(email=email, name=email.split("@")[0], role=role, password_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _login_as(client, session, email: str, role: Role) -> User:
    """Register through the API so the session cookie is set, then set the role."""
    client.post("/api/auth/register", json={"email": email, "password": "supersecret1", "name": "Tester"})
    user = session.exec(select(User).where(User.email == email)).first()
    user.role = role
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _event(session, slug: str) -> Event:
    owner = _user(session, f"{slug}-owner@example.com", Role.organizer)
    event = Event(
        slug=slug,
        name="Judging Event",
        start_at=utcnow() - timedelta(days=1),
        end_at=utcnow() + timedelta(days=2),
        created_by_id=owner.id,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def _submitted(session, event: Event, team_name: str, title: str, members: list[User]) -> Submission:
    team = Team(event_id=event.id, name=team_name)
    session.add(team)
    session.commit()
    session.refresh(team)
    for member in members:
        session.add(TeamMembership(team_id=team.id, user_id=member.id))
    submission = Submission(
        team_id=team.id,
        event_id=event.id,
        title=title,
        description="Seeded for judging tests.",
        status=SubmissionStatus.submitted,
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)
    return submission


def test_a_single_rubric_need_not_itself_sum_to_one(client, session):
    """An organizer builds a multi-rubric set up one rubric at a time, so a lone
    rubric summing to 0.6 is normal mid-setup -- only the combined set, checked
    when judges are assigned, has to reach 1.0 (see the test below)."""
    event = _event(session, "rubric-weights")
    _login_as(client, session, "rubric-org@example.com", Role.organizer)
    bad = [
        {"key": "a", "label": "Alpha", "weight": 0.3, "max_score": 10},
        {"key": "b", "label": "Beta", "weight": 0.3, "max_score": 10},
    ]
    r = client.post(f"/api/events/{event.id}/rubrics", json={"name": "Partial Rubric", "criteria": bad})
    assert r.status_code == 201, r.text


def test_assignment_is_refused_when_the_combined_rubric_weights_do_not_sum_to_one(client, session):
    event = _event(session, "rubric-weights-gate")
    p1 = _user(session, "rubric-weights-gate-p@example.com", Role.participant)
    _submitted(session, event, "Team RWG", "Weighty", [p1])
    _user(session, "rubric-weights-gate-judge@example.com", Role.judge)
    _login_as(client, session, "rubric-weights-gate-org@example.com", Role.organizer)
    bad = [
        {"key": "a", "label": "Alpha", "weight": 0.3, "max_score": 10},
        {"key": "b", "label": "Beta", "weight": 0.3, "max_score": 10},
    ]
    client.post(f"/api/events/{event.id}/rubrics", json={"name": "Partial Rubric", "criteria": bad})

    r = client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 1})
    assert r.status_code == 409, r.text
    # The message must name the actual total, not just say "invalid".
    assert "0.6" in r.text


def test_rubric_accepts_weights_summing_to_one(client, session):
    event = _event(session, "rubric-ok")
    _login_as(client, session, "rubric-ok-org@example.com", Role.organizer)
    r = client.post(f"/api/events/{event.id}/rubrics", json={"name": "Good Rubric", "criteria": VALID_CRITERIA})
    assert r.status_code == 201, r.text
    assert len(r.json()["criteria"]) == 2


def test_rubric_rejects_duplicate_criterion_keys(client, session):
    event = _event(session, "rubric-dupe")
    _login_as(client, session, "rubric-dupe-org@example.com", Role.organizer)
    dupes = [
        {"key": "a", "label": "Alpha", "weight": 0.5, "max_score": 10},
        {"key": "a", "label": "Also Alpha", "weight": 0.5, "max_score": 10},
    ]
    r = client.post(f"/api/events/{event.id}/rubrics", json={"name": "Dupe Rubric", "criteria": dupes})
    assert r.status_code == 422


def test_assignment_run_is_idempotent(client, session):
    event = _event(session, "assign-idem")
    p1 = _user(session, "assign-p1@example.com", Role.participant)
    _submitted(session, event, "Team A", "Alpha", [p1])
    for i in range(3):
        _user(session, f"assign-judge{i}@example.com", Role.judge)

    _login_as(client, session, "assign-org@example.com", Role.organizer)
    client.post(f"/api/events/{event.id}/rubrics", json={"name": "Test Rubric", "criteria": VALID_CRITERIA})

    first = client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 3})
    assert first.status_code == 201, first.text
    assert first.json()["created"] == 3

    second = client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 3})
    assert second.status_code == 201
    assert second.json()["created"] == 0, "re-running must not duplicate assignments"
    assert second.json()["existing"] == 3

    rows = session.exec(select(JudgeAssignment).where(JudgeAssignment.event_id == event.id)).all()
    assert len(rows) == 3


def test_assignment_requires_a_rubric_first(client, session):
    event = _event(session, "assign-no-rubric")
    p1 = _user(session, "norubric-p@example.com", Role.participant)
    _submitted(session, event, "Team NR", "No Rubric", [p1])
    _user(session, "norubric-judge@example.com", Role.judge)
    _login_as(client, session, "norubric-org@example.com", Role.organizer)

    r = client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 3})
    assert r.status_code == 409
    assert "rubric" in r.json()["detail"].lower()


def test_assignment_reports_coverage_shortfall(client, session):
    event = _event(session, "assign-short")
    p1 = _user(session, "short-p@example.com", Role.participant)
    _submitted(session, event, "Team S", "Short", [p1])
    _user(session, "short-judge@example.com", Role.judge)  # only one judge
    _login_as(client, session, "short-org@example.com", Role.organizer)
    client.post(f"/api/events/{event.id}/rubrics", json={"name": "Test Rubric", "criteria": VALID_CRITERIA})

    r = client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 3})
    assert r.status_code == 201
    warnings = r.json()["coverage_warnings"]
    assert len(warnings) == 1 and warnings[0]["judges_short"] == 2


def test_rubric_cannot_change_once_scoring_has_started(client, session):
    event = _event(session, "rubric-locked")
    p1 = _user(session, "locked-p@example.com", Role.participant)
    _submitted(session, event, "Team L", "Locked", [p1])
    judge = _login_as(client, session, "locked-judge@example.com", Role.judge)

    client.post("/api/auth/logout")
    _login_as(client, session, "locked-org@example.com", Role.organizer)
    created = client.post(f"/api/events/{event.id}/rubrics", json={"name": "Test Rubric", "criteria": VALID_CRITERIA})
    rubric_id = created.json()["id"]
    client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 1})

    assignment = session.exec(select(JudgeAssignment).where(JudgeAssignment.judge_id == judge.id)).first()
    assert assignment is not None
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "locked-judge@example.com", "password": "supersecret1"})
    r = client.put(f"/api/assignments/{assignment.id}/score", json={"values": {"impact": 8, "execution": 7}})
    assert r.status_code == 200, r.text

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "locked-org@example.com", "password": "supersecret1"})
    changed = [
        {"key": "impact", "label": "Impact", "weight": 0.8, "max_score": 10},
        {"key": "execution", "label": "Execution", "weight": 0.2, "max_score": 10},
    ]
    r = client.put(f"/api/events/{event.id}/rubrics/{rubric_id}", json={"name": "Reweighted Rubric", "criteria": changed})
    assert r.status_code == 409, "changing weights after scoring would invalidate the scores already given"


def test_judge_progress_counts_only_their_own_assignments(client, session):
    event = _event(session, "progress")
    p1 = _user(session, "prog-p@example.com", Role.participant)
    s1 = _submitted(session, event, "Team P1", "Prog One", [p1])
    s2 = _submitted(session, event, "Team P2", "Prog Two", [p1])
    judge_a = _login_as(client, session, "prog-judge-a@example.com", Role.judge)
    judge_b = _user(session, "prog-judge-b@example.com", Role.judge)

    session.add(JudgeAssignment(event_id=event.id, submission_id=s1.id, judge_id=judge_a.id))
    session.add(JudgeAssignment(event_id=event.id, submission_id=s2.id, judge_id=judge_b.id))
    session.commit()

    r = client.get("/api/judge/assignments")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1, "a judge must not see another judge's assignments"
    assert body["completed"] == 0
    assert body["pending"][0]["submission_id"] == s1.id


def test_scoring_sheet_is_scoped_to_the_owning_judge(client, session):
    event = _event(session, "sheet-scope")
    p1 = _user(session, "sheet-p@example.com", Role.participant)
    submission = _submitted(session, event, "Team Sheet", "Sheet Entry", [p1])
    owner = _user(session, "sheet-owner@example.com", Role.judge)
    session.add(Rubric(event_id=event.id, name="Sheet Rubric", criteria=VALID_CRITERIA))
    session.commit()
    assignment = JudgeAssignment(event_id=event.id, submission_id=submission.id, judge_id=owner.id)
    session.add(assignment)
    session.commit()
    session.refresh(assignment)

    # A different judge is refused outright, not given a partial sheet.
    _login_as(client, session, "sheet-other@example.com", Role.judge)
    assert client.get(f"/api/assignments/{assignment.id}/sheet").status_code == 403


def test_scoring_sheet_carries_the_rubric_and_the_judges_own_score(client, session):
    event = _event(session, "sheet-content")
    p1 = _user(session, "sheetc-p@example.com", Role.participant)
    submission = _submitted(session, event, "Team SC", "Sheet Content", [p1])
    judge = _login_as(client, session, "sheetc-judge@example.com", Role.judge)
    session.add(Rubric(event_id=event.id, name="Content Rubric", criteria=VALID_CRITERIA))
    session.commit()
    assignment = JudgeAssignment(event_id=event.id, submission_id=submission.id, judge_id=judge.id)
    session.add(assignment)
    session.commit()
    session.refresh(assignment)

    sheet = client.get(f"/api/assignments/{assignment.id}/sheet")
    assert sheet.status_code == 200, sheet.text
    body = sheet.json()
    assert body["submission_title"] == "Sheet Content"
    assert len(body["rubrics"]) == 1
    assert body["rubrics"][0]["rubric_name"] == "Content Rubric"
    assert [c["key"] for c in body["rubrics"][0]["criteria"]] == ["impact", "execution"]
    assert body["my_values"] is None, "nothing scored yet"

    client.put(f"/api/assignments/{assignment.id}/score", json={"values": {"impact": 6, "execution": 8}})
    body = client.get(f"/api/assignments/{assignment.id}/sheet").json()
    assert body["my_values"] == {"impact": 6, "execution": 8}
    assert body["my_raw_total"] == pytest.approx(7.0)  # 0.5*6 + 0.5*8


def test_score_must_cover_every_criterion_and_stay_in_range(client, session):
    event = _event(session, "score-validation")
    p1 = _user(session, "sv-p@example.com", Role.participant)
    submission = _submitted(session, event, "Team SV", "Validation Entry", [p1])
    judge = _login_as(client, session, "sv-judge@example.com", Role.judge)
    session.add(Rubric(event_id=event.id, name="Validation Rubric", criteria=VALID_CRITERIA))
    session.commit()
    assignment = JudgeAssignment(event_id=event.id, submission_id=submission.id, judge_id=judge.id)
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    url = f"/api/assignments/{assignment.id}/score"

    partial = client.put(url, json={"values": {"impact": 5}})
    assert partial.status_code == 422 and "execution" in partial.json()["detail"]

    unknown = client.put(url, json={"values": {"impact": 5, "execution": 5, "bogus": 5}})
    assert unknown.status_code == 422 and "bogus" in unknown.json()["detail"]

    too_high = client.put(url, json={"values": {"impact": 11, "execution": 5}})
    assert too_high.status_code == 422 and "between 0 and 10" in too_high.json()["detail"]

    negative = client.put(url, json={"values": {"impact": -1, "execution": 5}})
    assert negative.status_code == 422

    ok = client.put(url, json={"values": {"impact": 10, "execution": 4}})
    assert ok.status_code == 200 and ok.json()["raw_total"] == pytest.approx(7.0)


def test_rescoring_updates_rather_than_duplicating(client, session):
    event = _event(session, "rescore")
    p1 = _user(session, "rs-p@example.com", Role.participant)
    submission = _submitted(session, event, "Team RS", "Rescore Entry", [p1])
    judge = _login_as(client, session, "rs-judge@example.com", Role.judge)
    session.add(Rubric(event_id=event.id, name="Rescore Rubric", criteria=VALID_CRITERIA))
    session.commit()
    assignment = JudgeAssignment(event_id=event.id, submission_id=submission.id, judge_id=judge.id)
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    url = f"/api/assignments/{assignment.id}/score"

    first = client.put(url, json={"values": {"impact": 4, "execution": 4}}).json()
    second = client.put(url, json={"values": {"impact": 9, "execution": 9}}).json()
    assert first["id"] == second["id"], "re-scoring must edit the same row"
    assert second["raw_total"] == pytest.approx(9.0)

    from app.scoring.models import Score as ScoreModel
    rows = session.exec(select(ScoreModel).where(ScoreModel.assignment_id == assignment.id)).all()
    assert len(rows) == 1
