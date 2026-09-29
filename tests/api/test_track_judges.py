"""Track judges (DOGFOOD T2: "A track judge must never see another track").

The pure algorithm first, then the endpoints: assignment keeps track judges in
their track, and every judge read or write of an entry outside it is a 403,
even when an assignment row somehow exists.
"""
from dataclasses import dataclass
from datetime import timedelta

from sqlmodel import select

from app.auth.models import Role, User
from app.events.models import Event
from app.judging.assignment import assign_judges, outside_track
from app.judging.models import EventJudge, JudgeAssignment, Rubric
from app.scoring.models import Score
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow

CRITERIA = [
    {"key": "impact", "label": "Impact", "weight": 0.5, "max_score": 10},
    {"key": "execution", "label": "Execution", "weight": 0.5, "max_score": 10},
]


@dataclass
class FakeSubmission:
    id: int
    team_id: int
    track: str = ""
    event_id: int = 1


@dataclass
class FakeJudge:
    id: int


def _pairs(assignments) -> set[tuple[int, int]]:
    return {(a.submission_id, a.judge_id) for a in assignments}


# ---------------------------------------------------------------------------
# The pure algorithm
# ---------------------------------------------------------------------------

def test_outside_track_rule():
    assert not outside_track(None, "Productivity"), "an untracked judge takes any track"
    assert not outside_track(None, ""), "an untracked judge takes an entry with no track"
    assert not outside_track("Productivity", "Productivity")
    assert outside_track("Productivity", "Developer Tools")
    assert outside_track("Productivity", ""), "an entry with no track goes to untracked judges only"


def test_a_track_judge_is_only_assigned_their_own_track():
    subs = [FakeSubmission(1, 10, "Tools"), FakeSubmission(2, 20, "Apps"), FakeSubmission(3, 30, "")]
    judges = [FakeJudge(1), FakeJudge(2), FakeJudge(3), FakeJudge(4)]
    tracks = {1: "Tools", 2: "Apps"}
    result = assign_judges(subs, judges, [], k=3, judge_tracks=tracks)
    pairs = _pairs(result)
    assert pairs == {(1, 1), (1, 3), (1, 4), (2, 2), (2, 3), (2, 4), (3, 3), (3, 4)}
    for sub_id, judge_id in pairs:
        track = next(s.track for s in subs if s.id == sub_id)
        assert not outside_track(tracks.get(judge_id), track)


def test_an_uncovered_track_falls_back_to_untracked_judges_and_reports_the_rest():
    subs = [FakeSubmission(1, 10, "Hardware")]
    judges = [FakeJudge(1), FakeJudge(2), FakeJudge(3)]
    # Nobody judges Hardware; judge 1 is another track's, so only 2 and 3 may take it.
    result = assign_judges(subs, judges, [], k=3, judge_tracks={1: "Apps"})
    assert _pairs(result) == {(1, 2), (1, 3)}, "never handed to another track's judge, left short instead"


def test_track_assignment_is_deterministic_and_conflict_aware():
    subs = [FakeSubmission(i, i * 10, "Tools" if i % 2 else "Apps") for i in range(1, 7)]
    judges = [FakeJudge(i) for i in range(1, 7)]
    tracks = {1: "Tools", 2: "Apps", 3: "Tools"}
    members = [type("M", (), {"team_id": 10, "user_id": 1})()]
    first = _pairs(assign_judges(subs, judges, members, k=3, judge_tracks=tracks))
    again = _pairs(assign_judges(list(reversed(subs)), list(reversed(judges)), members, k=3, judge_tracks=tracks))
    assert first == again
    assert (1, 1) not in first, "a judge still never scores their own team's entry"
    counts = {s.id: sum(1 for p in first if p[0] == s.id) for s in subs}
    assert all(n == 3 for n in counts.values())


def test_untracked_judges_are_unaffected_when_no_one_has_a_track():
    subs = [FakeSubmission(1, 10, "Tools"), FakeSubmission(2, 20, "Apps")]
    judges = [FakeJudge(1), FakeJudge(2), FakeJudge(3)]
    assert _pairs(assign_judges(subs, judges, [], k=2)) == _pairs(
        assign_judges(subs, judges, [], k=2, judge_tracks={})
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

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
    session.refresh(user)
    return user


def _relogin(client, email: str) -> None:
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})


def _event(session, slug: str) -> Event:
    owner = _user(session, f"{slug}-owner@example.com", Role.organizer)
    event = Event(
        slug=slug,
        name="Track Event",
        start_at=utcnow() - timedelta(days=3),
        end_at=utcnow() - timedelta(hours=1),
        tracks=["Tools", "Apps"],
        created_by_id=owner.id,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    session.add(Rubric(event_id=event.id, name="Rubric", criteria=CRITERIA))
    session.commit()
    return event


def _entry(session, event: Event, name: str, track: str) -> Submission:
    member = _user(session, f"{event.slug}-{name}@example.com", Role.participant)
    team = Team(event_id=event.id, name=name)
    session.add(team)
    session.commit()
    session.refresh(team)
    session.add(TeamMembership(team_id=team.id, user_id=member.id))
    submission = Submission(
        team_id=team.id, event_id=event.id, title=name, track=track, status=SubmissionStatus.submitted
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)
    return submission


def _panel(session, event: Event, judge: User, track: "str | None" = None) -> None:
    session.add(EventJudge(event_id=event.id, user_id=judge.id, track=track))
    session.commit()


def _assign(session, event: Event, submission: Submission, judge: User) -> JudgeAssignment:
    assignment = JudgeAssignment(event_id=event.id, submission_id=submission.id, judge_id=judge.id)
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    return assignment


def test_assignment_run_respects_tracks(client, session):
    event = _event(session, "track-run")
    tools = _entry(session, event, "tools", "Tools")
    apps = _entry(session, event, "apps", "Apps")
    tools_judge = _user(session, "track-run-tj@example.com", Role.judge)
    apps_judge = _user(session, "track-run-aj@example.com", Role.judge)
    anyone = _user(session, "track-run-any@example.com", Role.judge)
    _panel(session, event, tools_judge, "Tools")
    _panel(session, event, apps_judge, "Apps")
    _panel(session, event, anyone)
    _login_as(client, session, "track-run-org@example.com", Role.organizer)

    r = client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 3})
    assert r.status_code == 201, r.text
    pairs = {(a.submission_id, a.judge_id) for a in session.exec(select(JudgeAssignment))}
    assert pairs == {(tools.id, tools_judge.id), (tools.id, anyone.id), (apps.id, apps_judge.id), (apps.id, anyone.id)}
    # Two judges each, not three: reported, never covered by another track's judge.
    shorts = {w["submission_id"]: w["judges_short"] for w in r.json()["coverage_warnings"]}
    assert shorts == {tools.id: 1, apps.id: 1}


def test_setting_a_track_releases_unscored_cross_track_work_on_the_next_run(client, session):
    event = _event(session, "track-rerun")
    tools = _entry(session, event, "tools", "Tools")
    apps = _entry(session, event, "apps", "Apps")
    judge = _user(session, "track-rerun-j@example.com", Role.judge)
    other = _user(session, "track-rerun-o@example.com", Role.judge)
    _panel(session, event, judge)
    _panel(session, event, other)
    scored = _assign(session, event, tools, judge)
    _assign(session, event, apps, judge)
    session.add(Score(assignment_id=scored.id, submission_id=tools.id, judge_id=judge.id, values={}, raw_total=5))
    session.commit()
    _login_as(client, session, "track-rerun-org@example.com", Role.organizer)

    r = client.put(f"/api/events/{event.id}/judges/{judge.id}/track", json={"track": "Apps"})
    assert r.status_code == 200 and r.json()["track"] == "Apps"
    listed = {j["user_id"]: j["track"] for j in client.get(f"/api/events/{event.id}/judges").json()["judges"]}
    assert listed[judge.id] == "Apps"

    client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 1})
    mine = {a.submission_id for a in session.exec(select(JudgeAssignment).where(JudgeAssignment.judge_id == judge.id))}
    # The Tools score stands; the Apps entry is in their track and stays theirs.
    assert mine == {tools.id, apps.id}

    client.put(f"/api/events/{event.id}/judges/{judge.id}/track", json={"track": "Tools"})
    client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 1})
    mine = {a.submission_id for a in session.exec(select(JudgeAssignment).where(JudgeAssignment.judge_id == judge.id))}
    assert mine == {tools.id}, "the unscored Apps assignment is released"
    refilled = session.exec(select(JudgeAssignment).where(JudgeAssignment.submission_id == apps.id)).all()
    assert [a.judge_id for a in refilled] == [other.id], "and the gap is filled by a judge who may see it"


def test_track_must_be_one_of_the_events_tracks_and_is_organizer_only(client, session):
    event = _event(session, "track-valid")
    judge = _login_as(client, session, "track-valid-j@example.com", Role.judge)
    _panel(session, event, judge)
    url = f"/api/events/{event.id}/judges/{judge.id}/track"
    assert client.put(url, json={"track": "Tools"}).status_code == 403, "a judge can't choose their own track"

    _login_as(client, session, "track-valid-org@example.com", Role.organizer)
    assert client.put(url, json={"track": "Nope"}).status_code == 422
    assert client.put(url, json={"track": "Tools"}).json()["track"] == "Tools"
    assert client.put(url, json={"track": None}).json()["track"] is None


def test_a_cross_track_sheet_or_score_is_refused_even_with_an_assignment_row(client, session):
    event = _event(session, "track-403")
    apps = _entry(session, event, "apps", "Apps")
    tools = _entry(session, event, "tools", "Tools")
    judge = _login_as(client, session, "track-403-j@example.com", Role.judge)
    _panel(session, event, judge, "Tools")
    # Rows that should never exist for this judge, written by hand.
    stray = _assign(session, event, apps, judge)
    own = _assign(session, event, tools, judge)

    assert client.get(f"/api/assignments/{stray.id}/sheet").status_code == 403
    r = client.put(f"/api/assignments/{stray.id}/score", json={"values": {"impact": 5, "execution": 5}})
    assert r.status_code == 403
    assert session.exec(select(Score).where(Score.assignment_id == stray.id)).first() is None
    assert client.get(f"/api/assignments/{stray.id}/score").status_code == 403

    progress = client.get("/api/judge/assignments").json()
    assert [a["submission_id"] for a in progress["pending"]] == [tools.id], "the stray entry is never listed"

    assert client.get(f"/api/assignments/{own.id}/sheet").status_code == 200
    ok = client.put(f"/api/assignments/{own.id}/score", json={"values": {"impact": 5, "execution": 5}})
    assert ok.status_code == 200


def test_a_judge_score_from_before_a_track_is_hidden_from_them(client, session):
    event = _event(session, "track-hide")
    apps = _entry(session, event, "apps", "Apps")
    judge = _login_as(client, session, "track-hide-j@example.com", Role.judge)
    _panel(session, event, judge)
    assignment = _assign(session, event, apps, judge)
    r = client.put(f"/api/assignments/{assignment.id}/score", json={"values": {"impact": 5, "execution": 5}})
    assert r.status_code == 200
    assert len(client.get("/api/judges/me/scores").json()) == 1

    member = session.exec(select(EventJudge).where(EventJudge.user_id == judge.id)).first()
    member.track = "Tools"
    session.add(member)
    session.commit()
    assert client.get("/api/judges/me/scores").json() == []
    assert client.get(f"/api/assignments/{assignment.id}/score").status_code == 403


def test_an_untracked_judge_is_unaffected(client, session):
    event = _event(session, "track-none")
    apps = _entry(session, event, "apps", "Apps")
    blank = _entry(session, event, "blank", "")
    judge = _login_as(client, session, "track-none-j@example.com", Role.judge)
    _panel(session, event, judge)
    for submission in (apps, blank):
        assignment = _assign(session, event, submission, judge)
        assert client.get(f"/api/assignments/{assignment.id}/sheet").status_code == 200
        r = client.put(f"/api/assignments/{assignment.id}/score", json={"values": {"impact": 5, "execution": 5}})
        assert r.status_code == 200
    assert client.get("/api/judge/assignments").json()["completed"] == 2
