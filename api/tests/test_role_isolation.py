"""The cross-cutting 403 matrix (PLAN.md Phase 2).

Gate requirement: at least one negative-role test per mutating/sensitive
endpoint built so far. The matrix below is driven by a table, so adding an
endpoint without adding its negative cases is a visible omission rather than a
silent one.

Naming: `anon` is unauthenticated (expects 401 -- the caller has no identity),
every named role expects 403 (identity established, permission refused).
"""
from datetime import timedelta

import pytest
from sqlmodel import select

from app.auth.models import Role, User
from app.events.models import Event
from app.judging.models import JudgeAssignment, Rubric
from app.scoring.models import Score
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow

CRITERIA = [
    {"key": "impact", "label": "Impact", "weight": 0.5, "max_score": 10},
    {"key": "execution", "label": "Execution", "weight": 0.5, "max_score": 10},
]


@pytest.fixture()
def world(client, session):
    """One event with a rubric, one submitted entry, one assignment and one score,
    plus an account of every role that is *not* the owner of any of it."""
    organizer = User(email="iso-org@example.com", name="Org", role=Role.organizer, password_hash="x")
    session.add(organizer)
    session.commit()
    session.refresh(organizer)

    event = Event(
        slug="isolation-event",
        name="Isolation Event",
        start_at=utcnow() - timedelta(days=1),
        end_at=utcnow() + timedelta(days=2),
        created_by_id=organizer.id,
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    member = User(email="iso-member@example.com", name="Member", role=Role.participant, password_hash="x")
    session.add(member)
    session.commit()
    session.refresh(member)

    team = Team(event_id=event.id, name="Isolation Team")
    session.add(team)
    session.commit()
    session.refresh(team)
    session.add(TeamMembership(team_id=team.id, user_id=member.id))

    submission = Submission(
        team_id=team.id,
        event_id=event.id,
        title="Isolation Entry",
        description="Owned by someone else.",
        status=SubmissionStatus.submitted,
    )
    session.add(submission)
    session.add(Rubric(event_id=event.id, name="Isolation Rubric", criteria=CRITERIA))
    session.commit()
    session.refresh(submission)

    owning_judge = User(email="iso-judge-owner@example.com", name="Owner Judge", role=Role.judge, password_hash="x")
    session.add(owning_judge)
    session.commit()
    session.refresh(owning_judge)

    assignment = JudgeAssignment(event_id=event.id, submission_id=submission.id, judge_id=owning_judge.id)
    session.add(assignment)
    session.commit()
    session.refresh(assignment)

    score = Score(
        assignment_id=assignment.id,
        submission_id=submission.id,
        judge_id=owning_judge.id,
        values={"impact": 8, "execution": 8},
        raw_total=8.0,
    )
    session.add(score)
    session.commit()

    return {
        "event": event,
        "team": team,
        "submission": submission,
        "assignment": assignment,
        "owning_judge": owning_judge,
    }


def _become(client, session, role: Role) -> User:
    """Sign in as a fresh account of `role` that owns none of the fixture data."""
    email = f"iso-{role.value}-outsider@example.com"
    client.post("/api/auth/logout")
    r = client.post("/api/auth/register", json={"email": email, "password": "supersecret1", "name": "Outsider"})
    if r.status_code == 409:
        client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    user = session.exec(select(User).where(User.email == email)).first()
    user.role = role
    session.add(user)
    session.commit()
    session.refresh(user)
    # Re-login so the session cookie is attached to the now-promoted account.
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    return user


def _call(client, method: str, url: str, body):
    return getattr(client, method)(url, **({"json": body} if body is not None else {}))


# (method, url_template, body, roles_that_must_be_refused)
MATRIX = [
    # --- events (organizer/admin only) ------------------------------------
    ("post", "/api/events", {"name": "Nope", "slug": "nope-event",
                             "start_at": "2030-01-01T00:00:00Z", "end_at": "2030-01-02T00:00:00Z"},
     [Role.participant, Role.judge]),
    ("patch", "/api/events/{event_id}", {"name": "Renamed"}, [Role.participant, Role.judge]),
    ("delete", "/api/events/{event_id}", None, [Role.participant, Role.judge]),

    # --- teams (participant only) -----------------------------------------
    ("post", "/api/events/{event_id}/teams", {"name": "Outsider Team"}, [Role.judge, Role.organizer, Role.admin]),
    ("post", "/api/teams/join", {"invite_code": "whatever"}, [Role.judge, Role.organizer, Role.admin]),

    # --- rubric writes (organizer/admin only) ------------------------------
    ("put", "/api/events/{event_id}/rubric", {"name": "Hijacked", "criteria": CRITERIA},
     [Role.participant, Role.judge]),
    ("delete", "/api/events/{event_id}/rubric", None, [Role.participant, Role.judge]),

    # --- assignment run + full matrix (organizer/admin only) ---------------
    ("post", "/api/events/{event_id}/assignments", {"judges_per_submission": 3},
     [Role.participant, Role.judge]),
    ("get", "/api/events/{event_id}/assignments", None, [Role.participant, Role.judge]),

    # --- scoring (the assigned judge only) --------------------------------
    ("put", "/api/assignments/{assignment_id}/score", {"values": {"impact": 10, "execution": 10}},
     [Role.participant, Role.organizer, Role.admin, Role.judge]),
    ("get", "/api/assignments/{assignment_id}/score", None,
     [Role.participant, Role.organizer, Role.admin, Role.judge]),
    ("get", "/api/assignments/{assignment_id}/sheet", None,
     [Role.participant, Role.organizer, Role.admin, Role.judge]),

    # --- judge invitation (organizer/admin only) --------------------------
    # The one role with no self-service path; a participant or judge minting an
    # invite would be a straight privilege escalation.
    ("post", "/api/judge-invites", {"expires_in_days": 14}, [Role.participant, Role.judge]),
    ("get", "/api/judge-invites", None, [Role.participant, Role.judge]),

    # --- audit log (organizer/admin only) ---------------------------------
    ("get", "/api/audit", None, [Role.participant, Role.judge]),

    # --- results + exports (organizer/admin only) -------------------------
    ("get", "/api/events/{event_id}/results", None, [Role.participant, Role.judge]),
    ("get", "/api/events/{event_id}/export/users.csv", None, [Role.participant, Role.judge]),
    ("get", "/api/events/{event_id}/export/submissions.csv", None, [Role.participant, Role.judge]),
    ("get", "/api/events/{event_id}/export/assignments.csv", None, [Role.participant, Role.judge]),
    ("get", "/api/events/{event_id}/export/scores.csv", None, [Role.participant, Role.judge]),
    ("get", "/api/events/{event_id}/export/results.csv", None, [Role.participant, Role.judge]),
]


@pytest.mark.parametrize(
    "method,url,body,role",
    [(m, u, b, role) for m, u, b, roles in MATRIX for role in roles],
    ids=[f"{m.upper()}-{u}-as-{role.value}" for m, u, b, roles in MATRIX for role in roles],
)
def test_wrong_role_is_refused(client, session, world, method, url, body, role):
    _become(client, session, role)
    target = url.format(event_id=world["event"].id, assignment_id=world["assignment"].id)
    response = _call(client, method, target, body)
    assert response.status_code == 403, f"{method.upper()} {target} as {role.value} -> {response.status_code}"


@pytest.mark.parametrize(
    "method,url,body",
    [(m, u, b) for m, u, b, _ in MATRIX],
    ids=[f"{m.upper()}-{u}" for m, u, b, _ in MATRIX],
)
def test_anonymous_is_refused(client, session, world, method, url, body):
    client.post("/api/auth/logout")
    target = url.format(event_id=world["event"].id, assignment_id=world["assignment"].id)
    response = _call(client, method, target, body)
    assert response.status_code == 401, f"{method.upper()} {target} anonymously -> {response.status_code}"


# --- ownership, not just role ---------------------------------------------

def test_a_judge_cannot_score_another_judges_assignment(client, session, world):
    """require_role(judge) is not enough on its own: the assignment must be theirs."""
    _become(client, session, Role.judge)
    r = client.put(
        f"/api/assignments/{world['assignment'].id}/score",
        json={"values": {"impact": 10, "execution": 10}},
    )
    assert r.status_code == 403
    assert "different judge" in r.json()["detail"]


def test_a_judge_cannot_read_another_judges_score(client, session, world):
    _become(client, session, Role.judge)
    r = client.get(f"/api/assignments/{world['assignment'].id}/score")
    assert r.status_code == 403


def test_an_organizer_cannot_submit_a_score_through_the_judge_endpoint(client, session, world):
    """PLAN.md Phase 2, stated explicitly: organizers must not be able to score by
    calling a judge endpoint directly."""
    _become(client, session, Role.organizer)
    r = client.put(
        f"/api/assignments/{world['assignment'].id}/score",
        json={"values": {"impact": 10, "execution": 10}},
    )
    assert r.status_code == 403


def test_a_participant_sees_no_score_detail_anywhere(client, session, world):
    _become(client, session, Role.participant)
    assert client.get(f"/api/events/{world['event'].id}/results").status_code == 403
    assert client.get(f"/api/events/{world['event'].id}/export/scores.csv").status_code == 403
    assert client.get(f"/api/assignments/{world['assignment'].id}/score").status_code == 403
    # The public gallery still works, and still carries no score data.
    gallery = client.get(f"/api/gallery?event_id={world['event'].id}")
    assert gallery.status_code == 200
    for row in gallery.json():
        assert "raw_total" not in row and "values" not in row and "z_bar" not in row


def test_a_non_member_cannot_touch_another_teams_submission(client, session, world):
    _become(client, session, Role.participant)
    team_id = world["team"].id
    assert client.get(f"/api/teams/{team_id}").status_code == 403
    assert client.get(f"/api/teams/{team_id}/submission").status_code == 403
    assert client.patch(f"/api/teams/{team_id}/submission", json={"title": "Hijack"}).status_code == 403
    assert client.post(f"/api/teams/{team_id}/submission/submit").status_code == 403


# --- Phase 3: voting and comments -----------------------------------------

def test_voting_requires_a_signed_in_user_but_any_role_may_take_part(client, session, world):
    """Voting is a community action, not a privileged one: every signed-in role
    can vote. Only anonymity is refused."""
    from app.events.models import Event

    event = session.get(Event, world["event"].id)
    event.voting_enabled = True
    session.add(event)
    session.commit()
    submission_id = world["submission"].id

    client.post("/api/auth/logout")
    assert client.post(f"/api/submissions/{submission_id}/vote").status_code == 401
    assert client.post(f"/api/submissions/{submission_id}/comments", json={"body": "Anon"}).status_code == 401

    for role in (Role.participant, Role.judge, Role.organizer):
        _become(client, session, role)
        r = client.post(f"/api/submissions/{submission_id}/vote")
        assert r.status_code in (200, 409), f"{role.value} could not vote: {r.status_code} {r.text}"


def test_one_user_cannot_delete_another_users_comment(client, session, world):
    submission_id = world["submission"].id
    author = _become(client, session, Role.participant)
    comment_id = client.post(
        f"/api/submissions/{submission_id}/comments", json={"body": "Written by the author."}
    ).json()["id"]
    assert author is not None

    _become(client, session, Role.judge)
    assert client.delete(f"/api/comments/{comment_id}").status_code == 403


def test_hidden_results_are_withheld_from_every_non_organizer_role(client, session, world):
    """The check is on the response body, not on whether the UI drew a control."""
    from datetime import timedelta

    from app.events.models import Event
    from app.timeutil import utcnow

    event = session.get(Event, world["event"].id)
    event.voting_enabled = True
    event.results_hidden_until = utcnow() + timedelta(days=1)
    session.add(event)
    session.commit()

    for role in (Role.participant, Role.judge):
        _become(client, session, role)
        assert client.get(f"/api/events/{event.id}/public-results").status_code == 425
        gallery = client.get(f"/api/gallery?event_id={event.id}").json()
        for row in gallery:
            assert row["votes"] is None, f"{role.value} received a vote count during the hidden window"

    _become(client, session, Role.organizer)
    assert client.get(f"/api/events/{event.id}/public-results").status_code == 200


# --- the two evaluation mechanisms stay separate (JUDGING.md role model) ---

def test_community_votes_do_not_affect_normalised_judging_results(client, session, world):
    """JUDGING.md states that vote counts never enter the judging pipeline.

    Structurally that holds because `scoring/` never imports `Vote`, but the claim is
    load-bearing for the normalisation's defensibility, so it is pinned here: pile votes
    onto one submission and the normalised standings must not move.
    """
    from app.events.models import Event
    from app.voting.models import Vote

    event = session.get(Event, world["event"].id)
    event.voting_enabled = True
    event.results_hidden_until = None
    session.add(event)
    session.commit()

    _become(client, session, Role.organizer)
    before = client.get(f"/api/events/{event.id}/results").json()

    # Twenty votes for the one submission, cast directly so no rate limit interferes.
    for i in range(20):
        voter = User(
            email=f"ballot-stuffer-{i}@example.com",
            name=f"Voter {i}",
            role=Role.participant,
            password_hash="x",
        )
        session.add(voter)
        session.commit()
        session.refresh(voter)
        session.add(
            Vote(event_id=event.id, submission_id=world["submission"].id, user_id=voter.id)
        )
    session.commit()

    after = client.get(f"/api/events/{event.id}/results").json()
    assert after == before, "community votes must not move the judged ranking"


def test_a_participant_cannot_score_even_their_own_teams_submission(client, session, world):
    """There is no peer-review path: being on the team is not a route to scoring it,
    and neither is being a participant at all."""
    from app.auth.security import hash_password

    member_email = "iso-member@example.com"
    client.post("/api/auth/logout")
    # The seeded member owns the submission under test; give them a usable password.
    user = session.exec(select(User).where(User.email == member_email)).first()
    user.password_hash = hash_password("supersecret1")
    session.add(user)
    session.commit()
    assert (
        client.post("/api/auth/login", json={"email": member_email, "password": "supersecret1"}).status_code
        == 200
    )
    # Confirm the 403s below are refusals of an authenticated team member, not 401s in
    # disguise from a login that quietly failed.
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == member_email
    assert me.json()["role"] == "participant"

    assignment_id = world["assignment"].id
    assert client.put(
        f"/api/assignments/{assignment_id}/score",
        json={"values": {"impact": 10, "execution": 10}},
    ).status_code == 403
    assert client.get(f"/api/assignments/{assignment_id}/sheet").status_code == 403
    assert client.get(f"/api/events/{world['event'].id}/results").status_code == 403
