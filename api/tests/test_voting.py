"""Voting, comments, rate limiting and results hiding (PLAN.md Phase 3)."""
from datetime import timedelta

import pytest
from sqlmodel import select

from app.audit.models import AuditLog
from app.auth.models import Role, User
from app.events.models import Event
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow
from app.voting.models import Vote
from app.ratelimit import TokenBucketLimiter


# ---------------------------------------------------------------------------
# The token bucket, as a pure unit (PLAN.md: in-process, no external service)
# ---------------------------------------------------------------------------

def test_token_bucket_allows_up_to_capacity_then_refuses():
    limiter = TokenBucketLimiter(capacity=3, per_seconds=60.0)
    assert [limiter.check("k", now=0.0)[0] for _ in range(3)] == [True, True, True]
    allowed, retry_after = limiter.check("k", now=0.0)
    assert allowed is False
    assert retry_after > 0


def test_token_bucket_refills_over_time():
    limiter = TokenBucketLimiter(capacity=2, per_seconds=60.0)
    limiter.check("k", now=0.0)
    limiter.check("k", now=0.0)
    assert limiter.check("k", now=0.0)[0] is False
    # 30s at 2 tokens/60s is one whole token back.
    assert limiter.check("k", now=30.0)[0] is True


def test_token_bucket_keys_are_independent():
    limiter = TokenBucketLimiter(capacity=1, per_seconds=60.0)
    assert limiter.check("a", now=0.0)[0] is True
    assert limiter.check("a", now=0.0)[0] is False
    assert limiter.check("b", now=0.0)[0] is True, "one user must not exhaust another's budget"


def test_token_bucket_never_exceeds_capacity_after_a_long_idle():
    limiter = TokenBucketLimiter(capacity=2, per_seconds=60.0)
    limiter.check("k", now=0.0)
    assert limiter.check("k", now=100_000.0)[0] is True
    assert limiter.check("k", now=100_000.0)[0] is True
    assert limiter.check("k", now=100_000.0)[0] is False, "idle time must not bank extra tokens"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _user(session, email: str, role: Role = Role.participant) -> User:
    user = User(email=email, name=email.split("@")[0], role=role, password_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _login(client, session, email: str, role: Role = Role.participant) -> User:
    client.post("/api/auth/logout")
    r = client.post("/api/auth/register", json={"email": email, "password": "supersecret1", "name": "Voter"})
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


def _event(session, slug: str, *, voting: bool = True, hidden_until=None) -> Event:
    owner = _user(session, f"{slug}-owner@example.com", Role.organizer)
    event = Event(
        slug=slug,
        name="Voting Event",
        start_at=utcnow() - timedelta(days=1),
        end_at=utcnow() + timedelta(days=2),
        created_by_id=owner.id,
        voting_enabled=voting,
        results_hidden_until=hidden_until,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def _submission(session, event: Event, name: str, title: str) -> Submission:
    team = Team(event_id=event.id, name=name)
    session.add(team)
    session.commit()
    session.refresh(team)
    submission = Submission(
        team_id=team.id,
        event_id=event.id,
        title=title,
        description="Up for community voting.",
        status=SubmissionStatus.submitted,
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)
    return submission


def test_vote_once_then_duplicate_is_refused(client, session):
    event = _event(session, "vote-dup")
    sub = _submission(session, event, "Dup Team", "Dup Entry")
    _login(client, session, "dup-voter@example.com")

    first = client.post(f"/api/submissions/{sub.id}/vote")
    assert first.status_code == 200, first.text
    assert first.json()["voted"] is True

    second = client.post(f"/api/submissions/{sub.id}/vote")
    assert second.status_code == 409
    assert "already voted" in second.json()["detail"]

    assert len(session.exec(select(Vote).where(Vote.submission_id == sub.id)).all()) == 1


def test_the_unique_constraint_is_the_hard_guard(client, session):
    """Not the application check: inserting a duplicate directly must still fail."""
    from sqlalchemy.exc import IntegrityError

    event = _event(session, "vote-constraint")
    sub = _submission(session, event, "Constraint Team", "Constraint Entry")
    voter = _user(session, "constraint-voter@example.com")

    session.add(Vote(event_id=event.id, submission_id=sub.id, user_id=voter.id))
    session.commit()
    session.add(Vote(event_id=event.id, submission_id=sub.id, user_id=voter.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_vote_can_be_withdrawn_and_recast(client, session):
    event = _event(session, "vote-withdraw")
    sub = _submission(session, event, "Withdraw Team", "Withdraw Entry")
    _login(client, session, "withdraw-voter@example.com")

    client.post(f"/api/submissions/{sub.id}/vote")
    removed = client.delete(f"/api/submissions/{sub.id}/vote")
    assert removed.status_code == 200 and removed.json()["voted"] is False
    assert client.post(f"/api/submissions/{sub.id}/vote").status_code == 200


def test_voting_is_refused_when_the_event_has_it_switched_off(client, session):
    event = _event(session, "vote-closed", voting=False)
    sub = _submission(session, event, "Closed Team", "Closed Entry")
    _login(client, session, "closed-voter@example.com")

    r = client.post(f"/api/submissions/{sub.id}/vote")
    assert r.status_code == 409
    assert "not open" in r.json()["detail"]


def test_anonymous_cannot_vote(client, session):
    event = _event(session, "vote-anon")
    sub = _submission(session, event, "Anon Team", "Anon Entry")
    client.post("/api/auth/logout")
    assert client.post(f"/api/submissions/{sub.id}/vote").status_code == 401


def test_a_draft_submission_cannot_be_voted_on(client, session):
    event = _event(session, "vote-draft")
    team = Team(event_id=event.id, name="Draft Team")
    session.add(team)
    session.commit()
    session.refresh(team)
    draft = Submission(team_id=team.id, event_id=event.id, title="Draft", status=SubmissionStatus.draft)
    session.add(draft)
    session.commit()
    session.refresh(draft)

    _login(client, session, "draft-voter@example.com")
    assert client.post(f"/api/submissions/{draft.id}/vote").status_code == 404


# --- results hiding, enforced in the response ------------------------------

def test_vote_counts_are_withheld_from_the_response_while_results_are_hidden(client, session):
    event = _event(session, "hidden-window", hidden_until=utcnow() + timedelta(days=1))
    sub = _submission(session, event, "Hidden Team", "Hidden Entry")
    voter = _user(session, "hidden-prevoter@example.com")
    session.add(Vote(event_id=event.id, submission_id=sub.id, user_id=voter.id))
    session.commit()

    _login(client, session, "hidden-viewer@example.com")
    gallery = client.get(f"/api/gallery?event_id={event.id}").json()
    assert gallery[0]["votes"] is None, "the count must be absent from the payload, not merely hidden by the UI"

    detail = client.get(f"/api/submissions/{sub.id}").json()
    assert detail["votes"] is None


def test_public_results_are_refused_during_the_hidden_window_and_say_when(client, session):
    reveal = utcnow() + timedelta(days=1)
    event = _event(session, "hidden-results", hidden_until=reveal)
    _submission(session, event, "Hidden R Team", "Hidden R Entry")
    _login(client, session, "hidden-r-viewer@example.com")

    r = client.get(f"/api/events/{event.id}/public-results")
    assert r.status_code == 425
    # The message must explain *why* and *until when* (PLAN.md Phase 3 UX).
    assert "hidden until" in r.json()["detail"].lower()


def test_counts_appear_once_the_window_has_passed(client, session):
    event = _event(session, "revealed", hidden_until=utcnow() - timedelta(minutes=1))
    sub = _submission(session, event, "Revealed Team", "Revealed Entry")
    voter = _user(session, "revealed-prevoter@example.com")
    session.add(Vote(event_id=event.id, submission_id=sub.id, user_id=voter.id))
    session.commit()

    _login(client, session, "revealed-viewer@example.com")
    assert client.get(f"/api/gallery?event_id={event.id}").json()[0]["votes"] == 1
    results = client.get(f"/api/events/{event.id}/public-results")
    assert results.status_code == 200 and results.json()[0]["votes"] == 1


def test_organizers_see_results_during_the_window_but_participants_do_not(client, session):
    event = _event(session, "hidden-organizer", hidden_until=utcnow() + timedelta(days=1))
    sub = _submission(session, event, "Org View Team", "Org View Entry")
    voter = _user(session, "orgview-prevoter@example.com")
    session.add(Vote(event_id=event.id, submission_id=sub.id, user_id=voter.id))
    session.commit()

    _login(client, session, "orgview-participant@example.com", Role.participant)
    assert client.get(f"/api/events/{event.id}/public-results").status_code == 425

    _login(client, session, "orgview-organizer@example.com", Role.organizer)
    assert client.get(f"/api/events/{event.id}/public-results").status_code == 200


def test_sorting_by_votes_is_refused_while_results_are_hidden(client, session):
    event = _event(session, "hidden-sort", hidden_until=utcnow() + timedelta(days=1))
    _submission(session, event, "Sort Team", "Sort Entry")
    _login(client, session, "sort-viewer@example.com")
    assert client.get(f"/api/gallery?event_id={event.id}&order=votes").status_code == 425


# --- randomized ordering ---------------------------------------------------

def test_the_same_seed_gives_the_same_order_and_a_different_seed_does_not(client, session):
    event = _event(session, "shuffle")
    for i in range(8):
        _submission(session, event, f"Shuffle Team {i}", f"Shuffle Entry {i}")

    def order(seed: int) -> list[int]:
        return [s["id"] for s in client.get(f"/api/gallery?event_id={event.id}&order=random&seed={seed}").json()]

    # Stable within a session: no layout jank on repeat visits (PLAN.md Phase 3 UX).
    assert order(12345) == order(12345)
    assert any(order(12345) != order(seed) for seed in (1, 2, 3, 4, 5)), "the shuffle must actually shuffle"
    assert sorted(order(12345)) == sorted(order(999)), "shuffling must not drop or duplicate entries"


# --- comments --------------------------------------------------------------

def test_comment_round_trip(client, session):
    event = _event(session, "comment-basic")
    sub = _submission(session, event, "Comment Team", "Comment Entry")
    _login(client, session, "commenter@example.com")

    created = client.post(f"/api/submissions/{sub.id}/comments", json={"body": "Nice use of the audit trail."})
    assert created.status_code == 201, created.text
    assert created.json()["author_name"] == "Voter"

    listed = client.get(f"/api/submissions/{sub.id}/comments").json()
    assert [c["body"] for c in listed] == ["Nice use of the audit trail."]


def test_comment_validation_rejects_empty_and_overlong(client, session):
    event = _event(session, "comment-validate")
    sub = _submission(session, event, "Validate Team", "Validate Entry")
    _login(client, session, "validating-commenter@example.com")

    assert client.post(f"/api/submissions/{sub.id}/comments", json={"body": "  "}).status_code == 422
    assert client.post(f"/api/submissions/{sub.id}/comments", json={"body": "x" * 1001}).status_code == 422


def test_a_commenter_can_delete_their_own_but_not_someone_elses(client, session):
    event = _event(session, "comment-delete")
    sub = _submission(session, event, "Delete Team", "Delete Entry")
    _login(client, session, "author-commenter@example.com")
    comment_id = client.post(f"/api/submissions/{sub.id}/comments", json={"body": "Mine to remove."}).json()["id"]

    _login(client, session, "other-commenter@example.com")
    assert client.delete(f"/api/comments/{comment_id}").status_code == 403

    _login(client, session, "author-commenter@example.com")
    assert client.delete(f"/api/comments/{comment_id}").status_code == 204


def test_an_organizer_can_moderate_any_comment(client, session):
    event = _event(session, "comment-moderate")
    sub = _submission(session, event, "Moderate Team", "Moderate Entry")
    _login(client, session, "moderated-commenter@example.com")
    comment_id = client.post(f"/api/submissions/{sub.id}/comments", json={"body": "Needs moderating."}).json()["id"]

    _login(client, session, "moderator@example.com", Role.organizer)
    assert client.delete(f"/api/comments/{comment_id}").status_code == 204


def test_comments_stay_readable_while_results_are_hidden(client, session):
    """Comments are discussion, not score data."""
    event = _event(session, "comment-hidden", hidden_until=utcnow() + timedelta(days=1))
    sub = _submission(session, event, "Hidden C Team", "Hidden C Entry")
    _login(client, session, "hidden-commenter@example.com")
    client.post(f"/api/submissions/{sub.id}/comments", json={"body": "Still discussable."})
    assert len(client.get(f"/api/submissions/{sub.id}/comments").json()) == 1


# --- rate limiting through the endpoints -----------------------------------

def test_comment_rate_limit_returns_429_with_a_friendly_message(client, session):
    event = _event(session, "comment-ratelimit")
    sub = _submission(session, event, "RL Team", "RL Entry")
    _login(client, session, "rl-commenter@example.com")

    last = None
    for i in range(20):
        last = client.post(f"/api/submissions/{sub.id}/comments", json={"body": f"Comment number {i}."})
        if last.status_code == 429:
            break
    assert last.status_code == 429, "the comment limiter never engaged"
    detail = last.json()["detail"]
    assert "limit" in detail and "try again" in detail, detail
    assert "Retry-After" in last.headers


def test_vote_rate_limit_engages(client, session):
    event = _event(session, "vote-ratelimit")
    subs = [_submission(session, event, f"VRL Team {i}", f"VRL Entry {i}") for i in range(30)]
    _login(client, session, "rl-voter@example.com")

    last = None
    for sub in subs:
        last = client.post(f"/api/submissions/{sub.id}/vote")
        if last.status_code == 429:
            break
    assert last.status_code == 429, "the vote limiter never engaged"


# --- duplicate-vote detection flags, never blocks --------------------------

def test_a_shared_client_fingerprint_is_flagged_but_the_vote_still_counts(client, session):
    """Two accounts voting from one client is suspicious, not proof. The vote
    must go through and an organizer must be able to see the flag."""
    event = _event(session, "fingerprint")
    sub = _submission(session, event, "FP Team", "FP Entry")

    _login(client, session, "fp-first@example.com")
    assert client.post(f"/api/submissions/{sub.id}/vote").status_code == 200

    _login(client, session, "fp-second@example.com")
    second = client.post(f"/api/submissions/{sub.id}/vote")
    assert second.status_code == 200, "a shared fingerprint must never block a vote"

    assert len(session.exec(select(Vote).where(Vote.submission_id == sub.id)).all()) == 2
    flags = session.exec(
        select(AuditLog).where(AuditLog.action == "vote.duplicate_fingerprint_flagged")
    ).all()
    assert flags, "the suspicious repeat must be recorded for an organizer"


# --- audit -----------------------------------------------------------------

def test_votes_and_comments_are_audited(client, session):
    event = _event(session, "audit-wiring")
    sub = _submission(session, event, "Audit Team", "Audit Entry")
    _login(client, session, "audited-user@example.com")
    client.post(f"/api/submissions/{sub.id}/vote")
    client.post(f"/api/submissions/{sub.id}/comments", json={"body": "Audited comment."})

    actions = {a.action for a in session.exec(select(AuditLog))}
    assert {"vote.cast", "comment.added"} <= actions


def test_phase_1_and_2_actions_are_audited_too(client, session):
    """PLAN.md Phase 3: wire the *remaining* actions into the audit module."""
    event = _event(session, "audit-earlier")
    _login(client, session, "audit-participant@example.com", Role.participant)
    team = client.post(f"/api/events/{event.id}/teams", json={"name": "Audited Team"}).json()
    client.patch(f"/api/teams/{team['id']}/submission", json={"title": "T", "description": "D"})
    client.post(f"/api/teams/{team['id']}/submission/submit")

    actions = {a.action for a in session.exec(select(AuditLog))}
    assert "user.registered" in actions
    assert "team.created" in actions
    assert "submission.submitted" in actions


def test_the_audit_log_is_organizer_only(client, session):
    _login(client, session, "audit-nosy@example.com", Role.participant)
    assert client.get("/api/audit").status_code == 403
    client.post("/api/auth/logout")
    assert client.get("/api/audit").status_code == 401
    _login(client, session, "audit-organizer@example.com", Role.organizer)
    assert client.get("/api/audit").status_code == 200


def test_the_audit_log_has_no_write_path(client, session):
    """Append-only is only true if nothing can mutate it."""
    _login(client, session, "audit-writer@example.com", Role.admin)
    for method in ("post", "put", "patch"):
        r = getattr(client, method)("/api/audit", json={})
        assert r.status_code in (404, 405), f"{method.upper()} /api/audit -> {r.status_code}"
    assert client.delete("/api/audit").status_code in (404, 405)
    assert client.delete("/api/audit/1").status_code in (404, 405)


# --- voting access: open link / email-confirmed / authenticated (DOGFOOD T3) --

def _access_event(session, slug: str, access: str) -> Event:
    event = _event(session, slug)
    event.voting_access = access
    session.add(event)
    session.commit()
    return event


def _mail(monkeypatch, enabled: bool) -> list:
    from app.auth import mailer

    sent: list = []
    monkeypatch.setattr(mailer, "CONFIG", mailer.MailConfig("smtp.test" if enabled else "", 587, "starttls", "", "", "x <x@y>"))
    monkeypatch.setattr(mailer, "send_quietly", lambda to, subject, text, html=None: sent.append((to, text)))
    return sent


def test_authenticated_mode_refuses_guests_even_with_a_voter_cookie(client, session):
    open_event = _access_event(session, "acc-open-first", "open")
    open_sub = _submission(session, open_event, "Open Team", "Open Entry")
    assert client.post(f"/api/submissions/{open_sub.id}/vote").status_code == 200  # now holds an anon cookie

    event = _event(session, "acc-auth")
    sub = _submission(session, event, "Auth Team", "Auth Entry")
    r = client.post(f"/api/submissions/{sub.id}/vote")
    assert r.status_code == 401
    assert r.json()["detail"] == "Log in to vote."


def test_open_link_guest_votes_once_sees_it_and_can_withdraw(client, session):
    event = _access_event(session, "acc-open", "open")
    sub = _submission(session, event, "Open Team 2", "Open Entry 2")

    first = client.post(f"/api/submissions/{sub.id}/vote")
    assert first.status_code == 200, first.text
    assert "voter" in client.cookies
    assert client.post(f"/api/submissions/{sub.id}/vote").status_code == 409, "same cookie, same voter"

    mine = client.get(f"/api/gallery?event_id={event.id}").json()
    assert mine[0]["voted_by_me"] is True
    assert client.get(f"/api/submissions/{sub.id}").json()["voted_by_me"] is True
    assert client.get("/api/voter/me").json() == {"voter": "anon"}

    assert client.delete(f"/api/submissions/{sub.id}/vote").status_code == 200
    vote_rows = session.exec(select(Vote).where(Vote.submission_id == sub.id)).all()
    assert vote_rows == []


def test_open_link_guests_share_the_per_client_rate_limit(client, session):
    """Clearing cookies mints a new open-link voter, but not a new budget."""
    event = _access_event(session, "acc-open-rl", "open")
    subs = [_submission(session, event, f"RL Team {i}", f"RL {i}") for i in range(21)]
    codes = []
    for s in subs:
        client.cookies.clear()
        codes.append(client.post(f"/api/submissions/{s.id}/vote").status_code)
    assert codes[:20] == [200] * 20
    assert codes[20] == 429


def test_email_mode_needs_a_confirmed_address(client, session, monkeypatch):
    sent = _mail(monkeypatch, enabled=True)
    event = _access_event(session, "acc-email", "email")
    sub = _submission(session, event, "Email Team", "Email Entry")

    r = client.post(f"/api/submissions/{sub.id}/vote")
    assert r.status_code == 401
    assert "Confirm your email" in r.json()["detail"]

    assert client.post(f"/api/events/{event.id}/voter-email", json={"email": "Guest@Example.com"}).status_code == 202
    assert len(sent) == 1 and sent[0][0] == "guest@example.com"
    link = next(w for w in sent[0][1].split() if "/api/voter-email/confirm" in w)
    path = link.split("localhost:8000", 1)[1]

    landed = client.get(path, follow_redirects=False)
    assert landed.status_code == 303
    assert landed.headers["location"] == f"/events/{event.slug}/gallery"
    assert client.post(f"/api/submissions/{sub.id}/vote").status_code == 200
    assert client.get("/api/voter/me").json() == {"voter": "email"}


def test_an_address_cannot_vote_as_a_guest_and_again_signed_in(client, session, monkeypatch):
    sent = _mail(monkeypatch, enabled=True)
    event = _access_event(session, "acc-email-dup", "email")
    sub = _submission(session, event, "Dup Email Team", "Dup Email Entry")

    client.post(f"/api/events/{event.id}/voter-email", json={"email": "twice@example.com"})
    link = next(w for w in sent[0][1].split() if "/api/voter-email/confirm" in w)
    client.get(link.split("localhost:8000", 1)[1], follow_redirects=False)
    assert client.post(f"/api/submissions/{sub.id}/vote").status_code == 200

    _login(client, session, "twice@example.com")
    r = client.post(f"/api/submissions/{sub.id}/vote")
    assert r.status_code == 409, "one address, one vote, whichever door it came through"


def test_a_tampered_or_open_mode_cookie_does_not_pass_the_email_gate(client, session, monkeypatch):
    _mail(monkeypatch, enabled=True)
    open_event = _access_event(session, "acc-gate-open", "open")
    open_sub = _submission(session, open_event, "Gate Open", "Gate Open Entry")
    client.post(f"/api/submissions/{open_sub.id}/vote")  # anon cookie

    event = _access_event(session, "acc-gate-email", "email")
    sub = _submission(session, event, "Gate Email", "Gate Email Entry")
    assert client.post(f"/api/submissions/{sub.id}/vote").status_code == 401

    client.cookies.set("voter", "email:forged")
    assert client.post(f"/api/submissions/{sub.id}/vote").status_code == 401
    bad = client.get("/api/voter-email/confirm?token=nonsense", follow_redirects=False)
    assert bad.status_code == 303 and "expired" in bad.headers["location"]


def test_email_mode_cannot_be_chosen_while_email_is_off(client, session, monkeypatch):
    _mail(monkeypatch, enabled=False)
    event = _event(session, "acc-setting")
    _login(client, session, "acc-setting-org@example.com", Role.organizer)

    r = client.patch(f"/api/events/{event.id}", json={"voting_access": "email"})
    assert r.status_code == 409
    assert "email set up" in r.json()["detail"]
    ok = client.patch(f"/api/events/{event.id}", json={"voting_access": "open"})
    assert ok.status_code == 200 and ok.json()["voting_access"] == "open"
    assert client.patch(f"/api/events/{event.id}", json={"voting_access": "everyone"}).status_code == 422


def test_guest_votes_are_audited_without_an_actor(client, session):
    event = _access_event(session, "acc-audit", "open")
    sub = _submission(session, event, "Audit Guest", "Audit Guest Entry")
    client.post(f"/api/submissions/{sub.id}/vote")
    entry = session.exec(
        select(AuditLog).where(AuditLog.action == "vote.cast", AuditLog.entity_id == sub.id)
    ).first()
    assert entry is not None and entry.actor_id is None
