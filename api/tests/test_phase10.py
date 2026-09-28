"""Phase 10 correctness fixes: per-event judge panels, one team per entrant per
event, and a sign-in attempt limit.

These three were bugs that made results wrong or unfair rather than features
that were missing, which is why they have their own file and are tested at the
endpoint level: the defect in each case was that the *server* allowed something,
so a test that only drove the UI would not have caught any of them.
"""
from datetime import timedelta

from sqlmodel import select

from app.auth.models import Role, User
from app.events.models import Event
from app.judging.models import EventJudge, JudgeAssignment
from app.ratelimit import login_account_limiter, login_ip_limiter
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow

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
        name=f"Event {slug}",
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
        description="Seeded.",
        status=SubmissionStatus.submitted,
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)
    return submission


# ---------------------------------------------------------------------------
# 10.1 -- judges belong to an event's panel, not to the whole platform
# ---------------------------------------------------------------------------


def test_assignment_only_uses_judges_on_this_events_panel(client, session):
    """The bug: assignment selected every account whose role was judge, so a judge
    invited for one hackathon was handed another hackathon's submissions."""
    event = _event(session, "panel-scope")
    entrant = _user(session, "panel-entrant@example.com", Role.participant)
    _submitted(session, event, "Panel Team", "Panel Project", [entrant])

    on_panel = _user(session, "on-panel@example.com", Role.judge)
    # A judge for some *other* event. Before Phase 10.1 they were assigned too.
    _user(session, "other-event-judge@example.com", Role.judge)
    session.add(EventJudge(event_id=event.id, judge_id=on_panel.id))
    session.commit()

    _login_as(client, session, "panel-org@example.com", Role.organizer)
    rub = client.post(f"/api/events/{event.id}/rubrics", json={"name": "Test Rubric", "criteria": VALID_CRITERIA})
    assert rub.status_code == 201, rub.text
    r = client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 3})
    assert r.status_code == 201, r.text

    assigned = {
        a.judge_id for a in session.exec(select(JudgeAssignment).where(JudgeAssignment.event_id == event.id))
    }
    assert assigned == {on_panel.id}, "only the event's own panel may be assigned"


def test_assignment_refuses_when_the_panel_is_empty(client, session):
    event = _event(session, "panel-empty")
    entrant = _user(session, "empty-entrant@example.com", Role.participant)
    _submitted(session, event, "Empty Team", "Empty Project", [entrant])
    _user(session, "unenrolled-judge@example.com", Role.judge)  # exists, not on the panel

    _login_as(client, session, "empty-org@example.com", Role.organizer)
    client.post(f"/api/events/{event.id}/rubrics", json={"name": "Test Rubric", "criteria": VALID_CRITERIA})
    r = client.post(f"/api/events/{event.id}/assignments", json={"judges_per_submission": 1})
    assert r.status_code == 409
    assert "no judges" in r.json()["detail"].lower()


def test_panel_endpoints_add_list_and_remove(client, session):
    event = _event(session, "panel-crud")
    judge = _user(session, "crud-judge@example.com", Role.judge)
    _login_as(client, session, "crud-org@example.com", Role.organizer)

    assert client.get(f"/api/events/{event.id}/judges").json() == []

    added = client.post(f"/api/events/{event.id}/judges", json={"judge_id": judge.id})
    assert added.status_code == 201, added.text
    # Adding twice is the same statement of intent, not an error.
    assert client.post(f"/api/events/{event.id}/judges", json={"judge_id": judge.id}).status_code in (200, 201)
    assert [j["judge_id"] for j in client.get(f"/api/events/{event.id}/judges").json()] == [judge.id]

    assert client.delete(f"/api/events/{event.id}/judges/{judge.id}").status_code == 204
    assert client.get(f"/api/events/{event.id}/judges").json() == []


def test_the_panel_cannot_be_used_to_grant_the_judge_role(client, session):
    """Composing a panel must not become a second way into the role -- invitation
    stays the only route in."""
    event = _event(session, "panel-escalate")
    participant = _user(session, "not-a-judge@example.com", Role.participant)
    _login_as(client, session, "escalate-org@example.com", Role.organizer)

    r = client.post(f"/api/events/{event.id}/judges", json={"judge_id": participant.id})
    assert r.status_code == 404
    session.refresh(participant)
    assert participant.role == Role.participant


def test_an_event_scoped_invitation_enrols_on_that_events_panel(client, session):
    event = _event(session, "invite-scoped")
    _login_as(client, session, "scoped-org@example.com", Role.organizer)
    invite = client.post("/api/judge-invites", json={"event_id": event.id}).json()
    assert invite["event_id"] == event.id
    assert invite["event_name"] == event.name

    client.post("/api/auth/logout")
    _login_as(client, session, "scoped-judge@example.com", Role.participant)
    redeemed = client.post(f"/api/judge-invites/{invite['token']}/redeem")
    assert redeemed.status_code == 200, redeemed.text
    assert redeemed.json()["event_id"] == event.id

    judge = session.exec(select(User).where(User.email == "scoped-judge@example.com")).first()
    assert judge.role == Role.judge
    enrolled = session.exec(
        select(EventJudge).where(EventJudge.event_id == event.id, EventJudge.judge_id == judge.id)
    ).first()
    assert enrolled is not None, "redeeming an event's invitation must put them on its panel"


def test_an_existing_judge_invited_to_a_second_event_is_enrolled_on_it(client, session):
    """Returning early for "already a judge" used to mean an established judge
    brought onto another event silently joined nothing."""
    first = _event(session, "second-a")
    second = _event(session, "second-b")
    judge = _login_as(client, session, "veteran@example.com", Role.judge)
    session.add(EventJudge(event_id=first.id, judge_id=judge.id))
    session.commit()
    client.post("/api/auth/logout")

    _login_as(client, session, "second-org@example.com", Role.organizer)
    invite = client.post("/api/judge-invites", json={"event_id": second.id}).json()
    client.post("/api/auth/logout")

    client.post("/api/auth/login", json={"email": "veteran@example.com", "password": "supersecret1"})
    r = client.post(f"/api/judge-invites/{invite['token']}/redeem")
    assert r.status_code == 200, r.text

    on_second = session.exec(
        select(EventJudge).where(EventJudge.event_id == second.id, EventJudge.judge_id == judge.id)
    ).first()
    assert on_second is not None


def test_invitations_can_be_listed_for_one_event(client, session):
    a = _event(session, "list-a")
    b = _event(session, "list-b")
    _login_as(client, session, "list-org@example.com", Role.organizer)
    client.post("/api/judge-invites", json={"event_id": a.id})
    client.post("/api/judge-invites", json={"event_id": b.id})

    only_a = client.get(f"/api/judge-invites?event_id={a.id}").json()
    assert [i["event_id"] for i in only_a] == [a.id]
    assert len(client.get("/api/judge-invites").json()) == 2


# ---------------------------------------------------------------------------
# 10.2 -- one entrant, one team, per event
# ---------------------------------------------------------------------------


def _join_code(session, event: Event, name: str) -> str:
    team = Team(event_id=event.id, name=name)
    session.add(team)
    session.commit()
    session.refresh(team)
    return team.invite_code


def test_a_participant_cannot_join_a_second_team_in_the_same_event(client, session):
    event = _event(session, "one-team-join")
    first_code = _join_code(session, event, "First Team")
    second_code = _join_code(session, event, "Second Team")
    _login_as(client, session, "joiner@example.com", Role.participant)

    assert client.post("/api/teams/join", json={"invite_code": first_code}).status_code == 200
    r = client.post("/api/teams/join", json={"invite_code": second_code})
    assert r.status_code == 409
    assert "already on a team for this event" in r.json()["detail"]


def test_a_participant_cannot_create_a_second_team_in_the_same_event(client, session):
    event = _event(session, "one-team-create")
    _login_as(client, session, "creator@example.com", Role.participant)

    assert client.post(f"/api/events/{event.id}/teams", json={"name": "Mine"}).status_code == 201
    r = client.post(f"/api/events/{event.id}/teams", json={"name": "Also Mine"})
    assert r.status_code == 409
    assert "already on a team for this event" in r.json()["detail"]


def test_the_limit_is_per_event_not_per_platform(client, session):
    """Competing in two different hackathons is normal and must stay allowed."""
    one = _event(session, "multi-event-one")
    two = _event(session, "multi-event-two")
    _login_as(client, session, "busy@example.com", Role.participant)

    assert client.post(f"/api/events/{one.id}/teams", json={"name": "Team One"}).status_code == 201
    assert client.post(f"/api/events/{two.id}/teams", json={"name": "Team Two"}).status_code == 201


# ---------------------------------------------------------------------------
# 10.4 -- sign-in attempt limit
# ---------------------------------------------------------------------------


def _registered(client, email: str, password: str = "supersecret1") -> None:
    """Create an account through the API so it has a real password hash.

    _user() stores a placeholder that passlib refuses to parse at all, which is
    harmless for accounts that never sign in and useless for these tests.
    """
    client.post("/api/auth/register", json={"email": email, "password": password, "name": "Tester"})
    client.post("/api/auth/logout")


def test_repeated_failed_sign_ins_are_eventually_refused(client, session):
    _registered(client, "target@example.com")
    seen_429 = False
    # The account bucket is the tighter of the two, so it trips first.
    for _ in range(login_account_limiter.capacity + 2):
        r = client.post("/api/auth/login", json={"email": "target@example.com", "password": "wrong-one"})
        if r.status_code == 429:
            seen_429 = True
            assert "Retry-After" in r.headers
            assert "too many sign-in attempts" in r.json()["detail"].lower()
            break
        assert r.status_code == 401
    assert seen_429, "a password can otherwise be guessed without limit"


def test_the_refusal_does_not_reveal_whether_the_account_exists(client, session):
    """Both buckets are spent before the password is checked, so an attacker cannot
    use the limiter itself to enumerate accounts."""
    _registered(client, "real@example.com")

    def responses_for(email: str) -> list[int]:
        login_ip_limiter.reset()
        login_account_limiter.reset()
        return [
            client.post("/api/auth/login", json={"email": email, "password": "wrong"}).status_code
            for _ in range(login_account_limiter.capacity + 1)
        ]

    assert responses_for("real@example.com") == responses_for("nobody@example.com")


def test_a_successful_sign_in_clears_that_accounts_failures(client, session):
    _registered(client, "fatfingers@example.com")
    for _ in range(login_account_limiter.capacity - 1):
        assert client.post(
            "/api/auth/login", json={"email": "fatfingers@example.com", "password": "nope"}
        ).status_code == 401

    ok = client.post("/api/auth/login", json={"email": "fatfingers@example.com", "password": "supersecret1"})
    assert ok.status_code == 200
    client.post("/api/auth/logout")

    # Budget restored: another wrong attempt is a plain 401, not an immediate 429.
    again = client.post("/api/auth/login", json={"email": "fatfingers@example.com", "password": "nope"})
    assert again.status_code == 401
