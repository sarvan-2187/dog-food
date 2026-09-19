"""PLAN.md Phase 10 - one section per item, each opening with the audit's own
"Found" scenario, which must fail on pre-Phase-10 code and pass now."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app.auth import mailer
from app.auth.models import Role, User
from app.auth.security import hash_password
from app.events.models import Event
from app.judging.models import EventJudge, JudgeAssignment, JudgeConflict, Rubric
from app.scoring.models import Score
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow

PASSWORD = "supersecret1"
CRITERIA = [
    {"key": "impact", "label": "Impact", "weight": 0.5, "max_score": 10, "description": "Who would use it?"},
    {"key": "execution", "label": "Execution", "weight": 0.5, "max_score": 10},
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _user(session, email: str, role: Role = Role.participant) -> User:
    user = User(email=email, name=f"{email.split('@')[0].title()} Person", role=role, password_hash=hash_password(PASSWORD))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _login(client, user: User) -> None:
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    assert r.status_code == 200, r.text


def _event(session, slug: str, *, closed: bool = True, **extra) -> Event:
    owner = _user(session, f"{slug}-owner@example.com", Role.organizer)
    now = utcnow()
    event = Event(
        slug=slug,
        name=slug.replace("-", " ").title(),
        start_at=now - timedelta(days=3),
        end_at=now - timedelta(hours=1) if closed else now + timedelta(days=2),
        created_by_id=owner.id,
        **extra,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    session.add(Rubric(event_id=event.id, name="Main Rubric", criteria=CRITERIA))
    session.commit()
    return event


def _entry(session, event: Event, name: str, members: list[User], *, track: str = "", submitted: bool = True) -> Submission:
    team = Team(event_id=event.id, name=name, captain_id=members[0].id if members else None)
    session.add(team)
    session.commit()
    session.refresh(team)
    for m in members:
        session.add(TeamMembership(team_id=team.id, user_id=m.id))
    sub = Submission(
        team_id=team.id,
        event_id=event.id,
        title=f"{name} project",
        track=track,
        status=SubmissionStatus.submitted if submitted else SubmissionStatus.draft,
    )
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub


def _pool(session, event: Event, *judges: User) -> None:
    for j in judges:
        session.add(EventJudge(event_id=event.id, user_id=j.id))
    session.commit()


def _score(session, assignment: JudgeAssignment, total: float) -> None:
    session.add(
        Score(
            assignment_id=assignment.id,
            submission_id=assignment.submission_id,
            judge_id=assignment.judge_id,
            values={"impact": total, "execution": total},
            raw_total=total,
        )
    )
    session.commit()


class FakeSMTP:
    sent: list = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        pass

    def login(self, *a):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture()
def mail_on(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(mailer, "CONFIG", mailer.MailConfig("smtp.test", 587, "starttls", "", "", "HackFlow <hf@test>"))
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    return FakeSMTP.sent


@pytest.fixture()
def mail_off(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("an SMTP connection was attempted with email off")

    monkeypatch.setattr(mailer, "CONFIG", mailer.MailConfig("", 587, "starttls", "", "", "HackFlow <x@y>"))
    monkeypatch.setattr(mailer.smtplib, "SMTP", refuse)


# ---------------------------------------------------------------------------
# 10.1 - judges belong to events
# ---------------------------------------------------------------------------

def test_found_a_judge_not_on_the_event_is_never_assigned_its_submissions(client, session):
    event = _event(session, "pool-scope")
    _entry(session, event, "Pool Team", [_user(session, "pool-p@example.com")])
    ours = _user(session, "pool-ours@example.com", Role.judge)
    theirs = _user(session, "pool-theirs@example.com", Role.judge)  # judges some other event
    _pool(session, event, ours)
    _login(client, _user(session, "pool-org@example.com", Role.organizer))

    r = client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 3})
    assert r.status_code == 201, r.text
    judges = {a.judge_id for a in session.exec(select(JudgeAssignment).where(JudgeAssignment.event_id == event.id))}
    assert judges == {ours.id}
    assert theirs.id not in judges


def test_an_event_with_no_judges_says_so(client, session):
    event = _event(session, "pool-empty")
    _entry(session, event, "Lonely Team", [_user(session, "lonely@example.com")])
    _user(session, "elsewhere-judge@example.com", Role.judge)
    _login(client, _user(session, "empty-org@example.com", Role.organizer))
    r = client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 1})
    assert r.status_code == 409
    assert "no judges" in r.json()["detail"]


def test_redeeming_an_event_invite_joins_that_events_pool(client, session):
    event_a = _event(session, "invite-a")
    event_b = _event(session, "invite-b")
    org = _user(session, "inv-org@example.com", Role.organizer)
    _login(client, org)
    first = client.post("/api/judge-invites", json={"event_id": event_a.id}).json()
    second = client.post("/api/judge-invites", json={"event_id": event_b.id}).json()

    person = _user(session, "inv-person@example.com")
    _login(client, person)
    assert client.post(f"/api/judge-invites/{first['token']}/redeem").status_code == 200
    # Already a judge, new event: joins that pool too, and the invite is used.
    r = client.post(f"/api/judge-invites/{second['token']}/redeem")
    assert r.status_code == 200 and r.json()["already_a_judge"] is True
    pools = {j.event_id for j in session.exec(select(EventJudge).where(EventJudge.user_id == person.id))}
    assert pools == {event_a.id, event_b.id}

    _login(client, org)
    listed = client.get(f"/api/judge-invites?event_id={event_a.id}").json()
    assert [i["id"] for i in listed] == [first["id"]]  # never another event's invitations


def test_a_judge_invite_without_an_event_is_refused(client, session):
    _login(client, _user(session, "noevent-org@example.com", Role.organizer))
    assert client.post("/api/judge-invites", json={}).status_code == 422
    assert client.get("/api/judge-invites").status_code == 422


def test_adding_an_existing_judge_by_email(client, session):
    event = _event(session, "add-existing")
    judge = _user(session, "existing-judge@example.com", Role.judge)
    participant = _user(session, "not-a-judge@example.com")
    _login(client, _user(session, "add-org@example.com", Role.organizer))
    assert client.post(f"/api/events/{event.id}/judges", json={"email": judge.email}).status_code == 201
    assert client.post(f"/api/events/{event.id}/judges", json={"email": participant.email}).status_code == 409
    assert client.post(f"/api/events/{event.id}/judges", json={"email": "ghost@example.com"}).status_code == 404
    assert [j["user_id"] for j in client.get(f"/api/events/{event.id}/judges").json()["judges"]] == [judge.id]


# ---------------------------------------------------------------------------
# 10.2 - one team per participant per event
# ---------------------------------------------------------------------------

def test_found_a_participant_cannot_be_on_two_teams_in_one_event(client, session):
    event = _event(session, "two-teams", closed=False)
    other_event = _event(session, "two-teams-other", closed=False)
    jordan = _user(session, "jordan-dup@example.com")
    _login(client, jordan)
    first = client.post(f"/api/events/{event.id}/teams", json={"name": "Codehawks"})
    assert first.status_code == 201

    again = client.post(f"/api/events/{event.id}/teams", json={"name": "Quiet Ledger"})
    assert again.status_code == 409
    assert "already on Codehawks" in again.json()["detail"]

    stranger = _user(session, "dup-stranger@example.com")
    _login(client, stranger)
    other_team = client.post(f"/api/events/{event.id}/teams", json={"name": "Other Team"}).json()
    _login(client, jordan)
    assert client.post("/api/teams/join", json={"invite_code": other_team["invite_code"]}).status_code == 409
    # A different event is fine.
    assert client.post(f"/api/events/{other_event.id}/teams", json={"name": "Elsewhere"}).status_code == 201


# ---------------------------------------------------------------------------
# 10.3 - judging opens only after submissions close
# ---------------------------------------------------------------------------

def test_found_assignment_and_scoring_are_refused_before_the_deadline(client, session):
    event = _event(session, "too-early", closed=False)
    sub = _entry(session, event, "Early Team", [_user(session, "early-p@example.com")])
    judge = _user(session, "early-judge@example.com", Role.judge)
    _pool(session, event, judge)

    _login(client, _user(session, "early-org@example.com", Role.organizer))
    r = client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 1})
    assert r.status_code == 409 and "Judging opens" in r.json()["detail"]

    # An assignment made before the fix still can't be scored early.
    legacy = JudgeAssignment(event_id=event.id, submission_id=sub.id, judge_id=judge.id)
    session.add(legacy)
    session.commit()
    _login(client, judge)
    r = client.put(f"/api/assignments/{legacy.id}/score", json={"values": {"impact": 5, "execution": 5}})
    assert r.status_code == 409


def test_closing_submissions_early_opens_judging(client, session):
    event = _event(session, "close-early", closed=False)
    _entry(session, event, "Close Team", [_user(session, "close-p@example.com")])
    _pool(session, event, _user(session, "close-judge@example.com", Role.judge))
    _login(client, _user(session, "close-org@example.com", Role.organizer))
    assert client.patch(f"/api/events/{event.id}", json={"end_at": utcnow().isoformat()}).status_code == 200
    assert client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 1}).status_code == 201


def test_a_judge_sees_when_judging_opens(client, session):
    event = _event(session, "opens-on", closed=False)
    judge = _user(session, "opens-judge@example.com", Role.judge)
    _pool(session, event, judge)
    _login(client, judge)
    [row] = client.get("/api/judge/events").json()
    assert row["event_id"] == event.id and row["judging_open"] is False


# ---------------------------------------------------------------------------
# 10.4 - login attempts are limited
# ---------------------------------------------------------------------------

def test_found_password_guessing_is_throttled_and_a_right_guess_is_still_refused(client, session):
    user = _user(session, "guessed@example.com")
    for _ in range(10):
        assert client.post("/api/auth/login", json={"email": user.email, "password": "wrong-guess"}).status_code == 401
    throttled = client.post("/api/auth/login", json={"email": user.email, "password": "wrong-guess"})
    assert throttled.status_code == 429
    # Once throttled, even the right password waits - otherwise the limit
    # wouldn't stop a guesser who ignores 429s.
    assert client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD}).status_code == 429


def test_throttling_looks_the_same_for_unknown_emails(client, session):
    _user(session, "known-throttle@example.com")
    known = unknown = None
    for _ in range(11):
        known = client.post("/api/auth/login", json={"email": "known-throttle@example.com", "password": "nope-nope"})
        unknown = client.post("/api/auth/login", json={"email": "unknown-throttle@example.com", "password": "nope-nope"})
    assert known.status_code == unknown.status_code == 429
    assert known.json()["detail"].split(" in about")[0] == unknown.json()["detail"].split(" in about")[0]


def test_a_successful_login_clears_the_failure_count(client, session):
    user = _user(session, "clears@example.com")
    for _ in range(9):
        client.post("/api/auth/login", json={"email": user.email, "password": "almost"})
    assert client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD}).status_code == 200
    for _ in range(9):
        assert client.post("/api/auth/login", json={"email": user.email, "password": "almost"}).status_code == 401


# ---------------------------------------------------------------------------
# 10.5 - project links
# ---------------------------------------------------------------------------

def test_found_links_are_saved_shown_to_judges_and_scripts_refused(client, session):
    event = _event(session, "links", closed=False)
    member = _user(session, "links-p@example.com")
    sub = _entry(session, event, "Links Team", [member])
    _login(client, member)
    url = f"/api/teams/{sub.team_id}/submission"
    assert client.patch(url, json={"repo_url": "javascript:alert(1)"}).status_code == 422
    assert client.patch(url, json={"demo_url": "not a url"}).status_code == 422
    r = client.patch(url, json={"repo_url": "https://github.com/x/y", "video_url": "https://youtu.be/abc"})
    assert r.status_code == 200, r.text
    assert r.json()["repo_url"] == "https://github.com/x/y"

    gallery = client.get(f"/api/gallery?event_id={event.id}").json()
    assert gallery[0]["repo_url"] == "https://github.com/x/y" and gallery[0]["video_url"] == "https://youtu.be/abc"

    judge = _user(session, "links-judge@example.com", Role.judge)
    assignment = JudgeAssignment(event_id=event.id, submission_id=sub.id, judge_id=judge.id)
    session.add(assignment)
    session.commit()
    _login(client, judge)
    sheet = client.get(f"/api/assignments/{assignment.id}/sheet").json()
    assert sheet["repo_url"] == "https://github.com/x/y"


# ---------------------------------------------------------------------------
# 10.6 - winners and awards
# ---------------------------------------------------------------------------

def _judged_event(session, slug: str, *, revealed: bool) -> tuple[Event, list[Submission]]:
    event = _event(
        session,
        slug,
        tracks=["Developer Tools", "Productivity"],
        prize_config={"prizes": [
            {"rank": "1st Place", "reward": "$500"},
            {"rank": "2nd Place", "reward": "$250"},
            {"rank": "Best Developer Tool", "reward": "$100"},
        ]},
        results_hidden_until=utcnow() - timedelta(minutes=1) if revealed else utcnow() + timedelta(days=1),
    )
    subs = [
        _entry(session, event, f"{slug}-a", [_user(session, f"{slug}-a@example.com")], track="Productivity"),
        _entry(session, event, f"{slug}-b", [_user(session, f"{slug}-b@example.com")], track="Developer Tools"),
        _entry(session, event, f"{slug}-c", [_user(session, f"{slug}-c@example.com")], track="Developer Tools"),
    ]
    judge = _user(session, f"{slug}-judge@example.com", Role.judge)
    for sub, total in zip(subs, (9.0, 7.0, 5.0)):
        a = JudgeAssignment(event_id=event.id, submission_id=sub.id, judge_id=judge.id)
        session.add(a)
        session.commit()
        _score(session, a, total)
    return event, subs


def test_found_winners_are_suggested_from_the_standings(client, session):
    event, (a, b, c) = _judged_event(session, "awards-suggest", revealed=False)
    _login(client, _user(session, "awards-org@example.com", Role.organizer))
    view = client.get(f"/api/events/{event.id}/awards").json()
    suggestions = {p["prize_rank"]: p["suggested_submission_id"] for p in view["prizes"]}
    assert suggestions == {"1st Place": a.id, "2nd Place": b.id, "Best Developer Tool": b.id}
    assert next(p for p in view["prizes"] if p["prize_rank"] == "Best Developer Tool")["track"] == "Developer Tools"


def test_winners_stay_hidden_until_the_reveal(client, session):
    event, (a, _b, _c) = _judged_event(session, "awards-hidden", revealed=False)
    _login(client, _user(session, "hidden-org@example.com", Role.organizer))
    r = client.put(f"/api/events/{event.id}/awards", json={"prize_rank": "1st Place", "submission_id": a.id})
    assert r.status_code == 200
    _login(client, _user(session, "hidden-viewer@example.com"))
    assert client.get(f"/api/events/{event.id}/winners").json() == {"visible": False, "winners": []}
    assert client.get(f"/api/submissions/{a.id}").json()["awards"] == []


def test_winners_appear_after_the_reveal(client, session):
    event, (a, _b, _c) = _judged_event(session, "awards-shown", revealed=True)
    _login(client, _user(session, "shown-org@example.com", Role.organizer))
    client.put(
        f"/api/events/{event.id}/awards", json={"prize_rank": "1st Place", "submission_id": a.id, "note": "Unanimous"}
    )
    _login(client, _user(session, "shown-viewer@example.com"))
    winners = client.get(f"/api/events/{event.id}/winners").json()
    assert winners["visible"] is True
    assert [(w["prize_rank"], w["submission_id"], w["note"]) for w in winners["winners"]] == [
        ("1st Place", a.id, "Unanimous")
    ]
    assert client.get(f"/api/submissions/{a.id}").json()["awards"] == ["1st Place"]


def test_an_award_must_go_to_a_submitted_project_in_the_event(client, session):
    event, _subs = _judged_event(session, "awards-guard", revealed=True)
    _other, (foreign, *_rest) = _judged_event(session, "awards-foreign", revealed=True)
    _login(client, _user(session, "guard-org@example.com", Role.organizer))
    r = client.put(f"/api/events/{event.id}/awards", json={"prize_rank": "1st Place", "submission_id": foreign.id})
    assert r.status_code == 422
    r = client.put(f"/api/events/{event.id}/awards", json={"prize_rank": "No Such Prize", "submission_id": None})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 10.7 - progress, removal, conflicts, reminders
# ---------------------------------------------------------------------------

def test_found_progress_shows_who_has_not_scored(client, session):
    event = _event(session, "progress-card")
    sub = _entry(session, event, "Progress Team", [_user(session, "progress-p@example.com")])
    done = _user(session, "done-judge@example.com", Role.judge)
    behind = _user(session, "behind-judge@example.com", Role.judge)
    _pool(session, event, done, behind)
    for j in (done, behind):
        session.add(JudgeAssignment(event_id=event.id, submission_id=sub.id, judge_id=j.id))
    session.commit()
    _score(session, session.exec(select(JudgeAssignment).where(JudgeAssignment.judge_id == done.id)).one(), 8)
    _login(client, _user(session, "progress-org@example.com", Role.organizer))
    body = client.get(f"/api/events/{event.id}/judges").json()
    assert (body["scored"], body["assigned"]) == (1, 2)
    assert body["judges"][0]["user_id"] == behind.id  # furthest behind first
    assert body["judges"][0]["scored"] == 0


def test_removing_a_judge_keeps_their_scores_and_a_rerun_only_fills_the_gap(client, session):
    event = _event(session, "remove-judge")
    subs = [_entry(session, event, f"Remove {i}", [_user(session, f"remove-p{i}@example.com")]) for i in range(2)]
    judges = [_user(session, f"remove-j{i}@example.com", Role.judge) for i in range(4)]
    _pool(session, event, *judges)
    _login(client, _user(session, "remove-org@example.com", Role.organizer))
    client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 2})
    leaving = judges[0]
    theirs = list(session.exec(select(JudgeAssignment).where(JudgeAssignment.judge_id == leaving.id)))
    _score(session, theirs[0], 6)

    r = client.delete(f"/api/events/{event.id}/judges/{leaving.id}")
    assert r.status_code == 200, r.text
    assert r.json()["kept_scores"] == 1

    rerun = client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 2})
    assert rerun.status_code == 201
    for sub in subs:
        count = len(session.exec(select(JudgeAssignment).where(JudgeAssignment.submission_id == sub.id)).all())
        assert count == 2, "a re-run tops each submission up to k, never past it"


def test_a_declared_conflict_is_never_handed_back(client, session):
    event = _event(session, "conflict")
    sub = _entry(session, event, "Conflict Team", [_user(session, "conflict-p@example.com")])
    judge = _user(session, "conflicted@example.com", Role.judge)
    spare = _user(session, "spare-judge@example.com", Role.judge)
    _pool(session, event, judge, spare)
    assignment = JudgeAssignment(event_id=event.id, submission_id=sub.id, judge_id=judge.id)
    session.add(assignment)
    session.commit()

    _login(client, judge)
    r = client.post(f"/api/assignments/{assignment.id}/conflict", json={"reason": "I mentored this team"})
    assert r.status_code == 204
    conflict = session.exec(select(JudgeConflict).where(JudgeConflict.judge_id == judge.id)).one()
    assert conflict.reason == "I mentored this team"

    _login(client, _user(session, "conflict-org@example.com", Role.organizer))
    client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 2})
    assigned = {a.judge_id for a in session.exec(select(JudgeAssignment).where(JudgeAssignment.submission_id == sub.id))}
    assert assigned == {spare.id}


def test_a_scored_assignment_cant_be_declared_a_conflict(client, session):
    event = _event(session, "conflict-late")
    sub = _entry(session, event, "Late Team", [_user(session, "late-p@example.com")])
    judge = _user(session, "late-judge@example.com", Role.judge)
    a = JudgeAssignment(event_id=event.id, submission_id=sub.id, judge_id=judge.id)
    session.add(a)
    session.commit()
    _score(session, a, 5)
    _login(client, judge)
    assert client.post(f"/api/assignments/{a.id}/conflict", json={}).status_code == 409


def test_reminders_need_email_and_are_limited(client, session, mail_off, monkeypatch):
    event = _event(session, "remind")
    sub = _entry(session, event, "Remind Team", [_user(session, "remind-p@example.com")])
    judge = _user(session, "remind-judge@example.com", Role.judge)
    _pool(session, event, judge)
    session.add(JudgeAssignment(event_id=event.id, submission_id=sub.id, judge_id=judge.id))
    session.commit()
    _login(client, _user(session, "remind-org@example.com", Role.organizer))
    assert client.post(f"/api/events/{event.id}/judges/{judge.id}/remind").status_code == 409  # email off

    FakeSMTP.sent = []
    monkeypatch.setattr(mailer, "CONFIG", mailer.MailConfig("smtp.test", 587, "starttls", "", "", "HackFlow <hf@test>"))
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    r = client.post(f"/api/events/{event.id}/judges/{judge.id}/remind")
    assert r.status_code == 200 and r.json()["remaining"] == 1
    assert FakeSMTP.sent[-1]["To"] == judge.email
    assert client.post(f"/api/events/{event.id}/judges/{judge.id}/remind").status_code == 429


# ---------------------------------------------------------------------------
# 10.8 - rules and public criteria
# ---------------------------------------------------------------------------

def test_found_participants_can_see_what_they_are_judged_on(client, session):
    event = _event(session, "criteria", closed=False)
    _login(client, _user(session, "criteria-viewer@example.com"))
    criteria = client.get(f"/api/events/{event.id}/criteria").json()
    assert [(c["label"], c["weight"], c["description"]) for c in criteria] == [
        ("Impact", 0.5, "Who would use it?"),
        ("Execution", 0.5, ""),
    ]
    assert all("values" not in c and "raw_total" not in c for c in criteria)


def test_rules_are_saved_as_plain_text(client, session):
    event = _event(session, "rules", closed=False)
    _login(client, _user(session, "rules-org@example.com", Role.organizer))
    r = client.patch(f"/api/events/{event.id}", json={"rules": "<b>Teams of 4</b>\nNo prebuilt code."})
    assert r.status_code == 200
    # Stored verbatim; the page renders it as text, never as HTML.
    assert r.json()["rules"] == "<b>Teams of 4</b>\nNo prebuilt code."


def test_criterion_descriptions_round_trip_through_the_rubric_builder(client, session):
    event = _event(session, "criteria-builder", closed=False)
    _login(client, _user(session, "builder-org@example.com", Role.organizer))
    r = client.post(
        f"/api/events/{event.id}/rubrics",
        json={"name": "Second Rubric", "criteria": [
            {"key": "polish", "label": "Polish", "weight": 0.1, "max_score": 10, "description": "Does it feel finished?"}
        ]},
    )
    assert r.status_code == 201, r.text
    labels = {c["label"]: c["description"] for c in client.get(f"/api/events/{event.id}/criteria").json()}
    assert labels["Polish"] == "Does it feel finished?"


# ---------------------------------------------------------------------------
# 10.9 - team management
# ---------------------------------------------------------------------------

def _open_team(session, slug: str, n: int) -> tuple[Event, Submission, list[User]]:
    event = _event(session, slug, closed=False)
    members = [_user(session, f"{slug}-{i}@example.com") for i in range(n)]
    return event, _entry(session, event, f"{slug} team", members, submitted=False), members


def test_found_members_can_leave_and_captaincy_passes_on(client, session):
    _ev, sub, (captain, second, _third) = _open_team(session, "leave", 3)
    _login(client, captain)
    assert client.post(f"/api/teams/{sub.team_id}/leave").status_code == 204
    session.expire_all()
    assert session.get(Team, sub.team_id).captain_id == second.id


def test_the_last_member_leaving_deletes_a_draft_team(client, session):
    _ev, sub, (only,) = _open_team(session, "last-out", 1)
    team_id = sub.team_id
    _login(client, only)
    assert client.post(f"/api/teams/{team_id}/leave").status_code == 204
    session.expire_all()
    assert session.get(Team, team_id) is None


def test_the_last_member_cant_abandon_a_submitted_entry(client, session):
    _ev, sub, (only,) = _open_team(session, "last-submitted", 1)
    sub.status = SubmissionStatus.submitted
    session.add(sub)
    session.commit()
    _login(client, only)
    assert client.post(f"/api/teams/{sub.team_id}/leave").status_code == 409


def test_only_the_captain_manages_the_team(client, session):
    _ev, sub, (captain, member) = _open_team(session, "captain", 2)
    _login(client, member)
    assert client.patch(f"/api/teams/{sub.team_id}", json={"name": "Hijacked"}).status_code == 403
    assert client.delete(f"/api/teams/{sub.team_id}/members/{captain.id}").status_code == 403

    _login(client, captain)
    assert client.patch(f"/api/teams/{sub.team_id}", json={"name": "Renamed Team"}).json()["name"] == "Renamed Team"
    old_code = session.get(Team, sub.team_id).invite_code
    new_code = client.post(f"/api/teams/{sub.team_id}/invite-code").json()["invite_code"]
    assert new_code != old_code
    _login(client, _user(session, "captain-outsider@example.com"))
    assert client.post("/api/teams/join", json={"invite_code": old_code}).status_code == 404  # old link dead

    _login(client, captain)
    r = client.post(f"/api/teams/{sub.team_id}/captain", json={"user_id": member.id})
    assert r.json()["captain_id"] == member.id
    _login(client, member)
    assert client.delete(f"/api/teams/{sub.team_id}/members/{captain.id}").status_code == 200


def test_teams_are_locked_after_the_deadline(client, session):
    event, sub, (captain, _member) = _open_team(session, "locked-team", 2)
    event.end_at = utcnow() - timedelta(minutes=1)
    session.add(event)
    session.commit()
    _login(client, captain)
    assert client.post(f"/api/teams/{sub.team_id}/leave").status_code == 400
    assert client.patch(f"/api/teams/{sub.team_id}", json={"name": "Too Late"}).status_code == 400


# ---------------------------------------------------------------------------
# 10.10 - admin user management and organizer invitations
# ---------------------------------------------------------------------------

def test_found_an_admin_can_promote_someone_to_organizer(client, session):
    admin = _user(session, "um-admin@example.com", Role.admin)
    person = _user(session, "um-person@example.com")
    _login(client, admin)
    found = client.get("/api/admin/users?q=um-person").json()
    assert [u["id"] for u in found["users"]] == [person.id]
    r = client.patch(f"/api/admin/users/{person.id}", json={"role": "organizer"})
    assert r.status_code == 200 and r.json()["role"] == "organizer"


def test_the_admin_role_is_never_granted_and_admins_cant_be_touched(client, session):
    admin = _user(session, "guard-admin@example.com", Role.admin)
    other_admin = _user(session, "guard-admin2@example.com", Role.admin)
    person = _user(session, "guard-person@example.com")
    _login(client, admin)
    assert client.patch(f"/api/admin/users/{person.id}", json={"role": "admin"}).status_code == 422
    assert client.patch(f"/api/admin/users/{other_admin.id}", json={"is_active": False}).status_code == 403
    assert client.patch(f"/api/admin/users/{admin.id}", json={"role": "participant"}).status_code == 403


def test_deactivating_signs_the_user_out_and_blocks_login(client, session):
    from app.main import app

    admin = _user(session, "deact-admin@example.com", Role.admin)
    person = _user(session, "deact-person@example.com")
    with TestClient(app) as their_browser:
        their_browser.post("/api/auth/login", json={"email": person.email, "password": PASSWORD})
        assert their_browser.get("/api/auth/me").status_code == 200
        _login(client, admin)
        assert client.patch(f"/api/admin/users/{person.id}", json={"is_active": False}).status_code == 200
        assert their_browser.get("/api/auth/me").status_code == 401
        r = their_browser.post("/api/auth/login", json={"email": person.email, "password": PASSWORD})
        assert r.status_code == 403 and "deactivated" in r.json()["detail"]


def test_organizer_invitations_are_admin_only_and_promote_on_redeem(client, session):
    organizer = _user(session, "oi-org@example.com", Role.organizer)
    admin = _user(session, "oi-admin@example.com", Role.admin)
    _login(client, organizer)
    assert client.post("/api/judge-invites", json={"grants_role": "organizer"}).status_code == 403
    _login(client, admin)
    invite = client.post("/api/judge-invites", json={"grants_role": "organizer"}).json()
    assert invite["grants_role"] == "organizer" and invite["event_id"] is None

    _login(client, _user(session, "oi-newcomer@example.com"))
    assert client.get(f"/api/judge-invites/{invite['token']}/preview").json()["grants_role"] == "organizer"
    r = client.post(f"/api/judge-invites/{invite['token']}/redeem")
    assert r.status_code == 200 and r.json()["role"] == "organizer"


def test_only_admins_reach_user_management(client, session):
    _login(client, _user(session, "um-organizer@example.com", Role.organizer))
    assert client.get("/api/admin/users").status_code == 403
    assert client.patch("/api/admin/users/1", json={"role": "judge"}).status_code == 403


# ---------------------------------------------------------------------------
# 10.11 - announcements
# ---------------------------------------------------------------------------

def test_found_an_organizer_can_tell_participants_something(client, session, mail_off):
    event = _event(session, "announce", closed=False)
    member = _user(session, "announce-p@example.com")
    _entry(session, event, "Announce Team", [member], submitted=False)
    _login(client, _user(session, "announce-org@example.com", Role.organizer))
    r = client.post(
        f"/api/events/{event.id}/announcements",
        json={"title": "Deadline moved", "body": "Submissions now close at 20:00."},
    )
    assert r.status_code == 201, r.text
    # Email off: asking to email is refused, and no connection is opened.
    refused = client.post(
        f"/api/events/{event.id}/announcements",
        json={"title": "Emailed", "body": "x", "email_participants": True},
    )
    assert refused.status_code == 409

    _login(client, member)
    assert [a["title"] for a in client.get(f"/api/events/{event.id}/announcements").json()] == ["Deadline moved"]
    assert [a["title"] for a in client.get("/api/announcements/mine").json()] == ["Deadline moved"]
    r = client.post(f"/api/events/{event.id}/announcements", json={"title": "Not me", "body": "x"})
    assert r.status_code == 403


def test_emailed_announcements_use_one_connection_and_are_limited(client, session, mail_on):
    event = _event(session, "announce-mail", closed=False)
    members = [_user(session, f"announce-mail-{i}@example.com") for i in range(3)]
    _entry(session, event, "Mail Team", members, submitted=False)
    _login(client, _user(session, "announce-mail-org@example.com", Role.organizer))
    r = client.post(
        f"/api/events/{event.id}/announcements",
        json={"title": "Demos at 5", "body": "Livestream link to follow.", "email_participants": True},
    )
    assert r.status_code == 201 and r.json()["email_queued"] == 3
    assert sorted(m["To"] for m in mail_on) == sorted(m.email for m in members)
    again = client.post(
        f"/api/events/{event.id}/announcements",
        json={"title": "Again", "body": "Too soon.", "email_participants": True},
    )
    assert again.status_code == 429


# ---------------------------------------------------------------------------
# 10.12 - draft events
# ---------------------------------------------------------------------------

def test_found_new_events_start_as_drafts_hidden_from_participants(client, session):
    organizer = _user(session, "draft-org@example.com", Role.organizer)
    _login(client, organizer)
    created = client.post(
        "/api/events",
        json={
            "slug": "secret-draft",
            "name": "Secret Draft",
            "start_at": "2030-01-01T00:00:00Z",
            "end_at": "2030-01-02T00:00:00Z",
        },
    ).json()
    assert created["status"] == "draft"

    _login(client, _user(session, "draft-viewer@example.com"))
    assert client.get("/api/events/secret-draft").status_code == 404  # 404, not 403: existence doesn't leak
    assert client.get(f"/api/events/id/{created['id']}").status_code == 404
    assert "secret-draft" not in [e["slug"] for e in client.get("/api/events").json()]
    assert client.post(f"/api/events/{created['id']}/teams", json={"name": "Early Birds"}).status_code == 404

    _login(client, organizer)
    assert client.post(f"/api/events/{created['id']}/publish").json()["status"] == "published"
    _login(client, _user(session, "draft-viewer2@example.com"))
    assert client.get("/api/events/secret-draft").status_code == 200


def test_an_event_with_teams_cant_go_back_to_draft(client, session):
    event = _event(session, "unpublish", closed=False)
    _entry(session, event, "Joined Team", [_user(session, "unpublish-p@example.com")], submitted=False)
    _login(client, _user(session, "unpublish-org@example.com", Role.organizer))
    assert client.post(f"/api/events/{event.id}/unpublish").status_code == 409


# ---------------------------------------------------------------------------
# 10.13 - edit your display name
# ---------------------------------------------------------------------------

def test_found_a_user_can_change_their_name(client, session):
    user = _user(session, "rename-me@example.com")
    _login(client, user)
    r = client.patch("/api/auth/me", json={"name": "  Jordan Q. Participant  "})
    assert r.status_code == 200 and r.json()["name"] == "Jordan Q. Participant"
    assert client.patch("/api/auth/me", json={"name": "J"}).status_code == 422
    assert client.get("/api/auth/me").json()["name"] == "Jordan Q. Participant"
