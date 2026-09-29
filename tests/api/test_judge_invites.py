"""Judge invitation (PLAN.md T2 "judge invitation and assignment", section 8.0).

`judge` is the one role with no self-service path. These tests exist mostly to
prove that stays true: the interesting cases are all the ways someone might try
to acquire the role without an organizer handing it to them.
"""
from datetime import timedelta

from sqlmodel import select

from app.audit.models import AuditLog
from app.auth.models import Role, User
from app.judging.models import JudgeInvite
from app.timeutil import utcnow


def _login(client, session, email: str, role: Role = Role.participant) -> User:
    client.post("/api/auth/logout")
    r = client.post("/api/auth/register", json={"email": email, "password": "supersecret1", "name": "Invitee"})
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


_event_count = 0


def _event_id(client) -> int:
    """A fresh event for the signed-in organizer - judge invitations belong to
    one (PLAN.md 10.1)."""
    global _event_count
    _event_count += 1
    r = client.post(
        "/api/events",
        json={
            "slug": f"invite-event-{_event_count}",
            "name": f"Invite Event {_event_count}",
            "start_at": "2030-01-01T00:00:00Z",
            "end_at": "2030-01-02T00:00:00Z",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _issue(client, **body) -> dict:
    body.setdefault("event_id", _event_id(client))
    r = client.post("/api/judge-invites", json={"expires_in_days": 14, **body})
    assert r.status_code == 201, r.text
    return r.json()


# --- the happy path -------------------------------------------------------

def test_organizer_invites_and_a_participant_becomes_a_judge(client, session):
    _login(client, session, "inv-org@example.com", Role.organizer)
    invite = _issue(client, invited_email="newjudge@example.com", note="Track: Developer Tools")
    assert invite["status"] == "open"

    _login(client, session, "newjudge@example.com", Role.participant)
    assert client.get("/api/auth/me").json()["role"] == "participant"
    # A participant cannot reach the judge dashboard before redeeming.
    assert client.get("/api/judge/assignments").status_code == 403

    r = client.post(f"/api/judge-invites/{invite['token']}/redeem")
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "judge" and r.json()["already_a_judge"] is False
    assert r.json()["event_id"] == invite["event_id"]

    assert client.get("/api/auth/me").json()["role"] == "judge"
    # ...and can now reach it, which is the whole point of the invitation.
    assert client.get("/api/judge/assignments").status_code == 200


def test_the_invitation_is_single_use(client, session):
    _login(client, session, "single-org@example.com", Role.organizer)
    invite = _issue(client)

    _login(client, session, "single-first@example.com", Role.participant)
    assert client.post(f"/api/judge-invites/{invite['token']}/redeem").status_code == 200

    _login(client, session, "single-second@example.com", Role.participant)
    r = client.post(f"/api/judge-invites/{invite['token']}/redeem")
    assert r.status_code == 409 and "already been used" in r.json()["detail"]
    assert client.get("/api/auth/me").json()["role"] == "participant"


def test_redeeming_twice_is_harmless_and_does_not_burn_a_second_invite(client, session):
    """A double-click or a refresh must not consume the organizer's next invitation."""
    _login(client, session, "twice-org@example.com", Role.organizer)
    first = _issue(client)
    second = _issue(client)

    _login(client, session, "twice-judge@example.com", Role.participant)
    assert client.post(f"/api/judge-invites/{first['token']}/redeem").json()["already_a_judge"] is False
    again = client.post(f"/api/judge-invites/{first['token']}/redeem")
    assert again.status_code == 200 and again.json()["already_a_judge"] is True

    stored = session.exec(select(JudgeInvite).where(JudgeInvite.token == second["token"])).first()
    assert stored.redeemed_at is None, "the second invitation must be untouched"


def test_an_expired_invitation_is_refused_server_side(client, session):
    _login(client, session, "exp-org@example.com", Role.organizer)
    invite = _issue(client)
    stored = session.exec(select(JudgeInvite).where(JudgeInvite.token == invite["token"])).first()
    stored.expires_at = utcnow() - timedelta(minutes=1)
    session.add(stored)
    session.commit()

    _login(client, session, "exp-judge@example.com", Role.participant)
    r = client.post(f"/api/judge-invites/{invite['token']}/redeem")
    assert r.status_code == 400 and "expired" in r.json()["detail"]
    assert client.get("/api/auth/me").json()["role"] == "participant"


# --- privilege escalation: the cases that matter -------------------------

def test_a_participant_cannot_issue_a_judge_invitation(client, session):
    """The whole control. If a participant can mint an invite, they can mint
    themselves sight of every score in the event."""
    _login(client, session, "escalate@example.com", Role.participant)
    assert client.post("/api/judge-invites", json={"expires_in_days": 14}).status_code == 403
    assert client.get("/api/judge-invites").status_code == 403


def test_a_judge_cannot_issue_further_judge_invitations(client, session):
    """No self-propagation: one compromised judge account must not become many."""
    _login(client, session, "propagate@example.com", Role.judge)
    assert client.post("/api/judge-invites", json={"expires_in_days": 14}).status_code == 403


def test_anonymous_can_neither_issue_nor_redeem(client, session):
    _login(client, session, "anon-org@example.com", Role.organizer)
    invite = _issue(client)
    client.post("/api/auth/logout")
    assert client.post("/api/judge-invites", json={"expires_in_days": 14}).status_code == 401
    # Redemption grants a role to a person, so it needs an account to grant it to.
    assert client.post(f"/api/judge-invites/{invite['token']}/redeem").status_code == 401


def test_registration_still_cannot_request_the_judge_role(client, session):
    """The invitation is an addition, not a loophole: signup is still participant-only."""
    r = client.post(
        "/api/auth/register",
        json={"email": "sneaky@example.com", "password": "supersecret1", "name": "Sneaky", "role": "judge"},
    )
    assert r.status_code == 201
    assert r.json()["role"] == "participant"


def test_an_organizer_redeeming_is_refused_rather_than_demoted(client, session):
    """Silently replacing organizer with judge would cost them their own event."""
    _login(client, session, "self-org@example.com", Role.organizer)
    invite = _issue(client)
    r = client.post(f"/api/judge-invites/{invite['token']}/redeem")
    assert r.status_code == 409
    assert "remove your ability to run events" in r.json()["detail"]
    assert client.get("/api/auth/me").json()["role"] == "organizer"

    stored = session.exec(select(JudgeInvite).where(JudgeInvite.token == invite["token"])).first()
    assert stored.redeemed_at is None, "a refused redemption must not consume the invitation"


# --- preview, listing, revocation ----------------------------------------

def test_preview_is_public_and_explains_a_dead_link_without_leaking(client, session):
    _login(client, session, "prev-org@example.com", Role.organizer)
    invite = _issue(client, invited_email="expected@example.com", note="internal note")
    client.post("/api/auth/logout")

    good = client.get(f"/api/judge-invites/{invite['token']}/preview")
    assert good.status_code == 200 and good.json()["valid"] is True
    # The preview must not disclose who it was for or the organizer's private note.
    assert "expected@example.com" not in good.text and "internal note" not in good.text

    bad = client.get("/api/judge-invites/not-a-real-token/preview")
    assert bad.status_code == 200 and bad.json()["valid"] is False
    assert "not valid" in bad.json()["reason"]


def test_listing_shows_status_and_who_redeemed(client, session):
    _login(client, session, "list-org@example.com", Role.organizer)
    invite = _issue(client)
    _login(client, session, "list-judge@example.com", Role.participant)
    client.post(f"/api/judge-invites/{invite['token']}/redeem")

    _login(client, session, "list-org@example.com", Role.organizer)
    rows = client.get(f"/api/judge-invites?event_id={invite['event_id']}").json()
    row = next(r for r in rows if r["id"] == invite["id"])
    assert row["status"] == "redeemed" and row["redeemed_by_name"] == "Invitee"


def test_an_unused_invitation_can_be_revoked_but_a_used_one_cannot(client, session):
    _login(client, session, "rev-org@example.com", Role.organizer)
    open_invite = _issue(client)
    used_invite = _issue(client)

    _login(client, session, "rev-judge@example.com", Role.participant)
    client.post(f"/api/judge-invites/{used_invite['token']}/redeem")

    _login(client, session, "rev-org@example.com", Role.organizer)
    assert client.delete(f"/api/judge-invites/{open_invite['id']}").status_code == 204
    r = client.delete(f"/api/judge-invites/{used_invite['id']}")
    assert r.status_code == 409 and "already been used" in r.json()["detail"]


def test_a_revoked_invitation_can_no_longer_be_redeemed(client, session):
    _login(client, session, "revdead-org@example.com", Role.organizer)
    invite = _issue(client)
    assert client.delete(f"/api/judge-invites/{invite['id']}").status_code == 204

    _login(client, session, "revdead-user@example.com", Role.participant)
    assert client.post(f"/api/judge-invites/{invite['token']}/redeem").status_code == 404
    assert client.get("/api/auth/me").json()["role"] == "participant"


def test_invite_lifecycle_is_audited(client, session):
    _login(client, session, "audit-inv-org@example.com", Role.organizer)
    invite = _issue(client)
    _login(client, session, "audit-inv-judge@example.com", Role.participant)
    client.post(f"/api/judge-invites/{invite['token']}/redeem")

    actions = {a.action for a in session.exec(select(AuditLog))}
    assert {"judge_invite.created", "judge_invite.redeemed"} <= actions
    redeemed = session.exec(
        select(AuditLog).where(AuditLog.action == "judge_invite.redeemed")
    ).first()
    assert redeemed.detail["previous_role"] == "participant"


def test_expiry_window_is_validated(client, session):
    _login(client, session, "win-org@example.com", Role.organizer)
    assert client.post("/api/judge-invites", json={"expires_in_days": 0}).status_code == 422
    assert client.post("/api/judge-invites", json={"expires_in_days": 91}).status_code == 422
    event_id = _event_id(client)
    assert client.post("/api/judge-invites", json={"expires_in_days": 1, "event_id": event_id}).status_code == 201
