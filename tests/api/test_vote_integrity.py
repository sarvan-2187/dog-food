"""Opt-in voting integrity: verified email, account cutoff, organizer void (THREAT-MODEL #25)."""
from datetime import timedelta

import pytest
from sqlmodel import select

from app.audit.models import AuditLog
from app.auth import mailer
from app.auth.models import Role, User
from app.auth.router import _verify_link
from app.events.models import Event
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team
from app.timeutil import utcnow
from app.voting.models import Vote


@pytest.fixture()
def mail_on(monkeypatch):
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        mailer, "CONFIG", mailer.MailConfig("smtp.test", 587, "starttls", "hf@test", "pw", "HackFlow <hf@test>")
    )
    monkeypatch.setattr(mailer, "send_quietly", lambda to, subject, text, html=None: sent.append((to, text)))
    return sent


def _login_as(client, session, email: str, role: Role = Role.participant) -> User:
    client.post("/api/auth/logout")
    if not session.exec(select(User).where(User.email == email)).first():
        client.post("/api/auth/register", json={"email": email, "password": "supersecret1", "name": "Tester"})
    user = session.exec(select(User).where(User.email == email)).first()
    user.role = role
    session.add(user)
    session.commit()
    client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    return user


def _voting_event(session, **rules) -> tuple[Event, Submission]:
    owner = User(email="vi-owner@example.com", name="Owner", role=Role.organizer, password_hash="x")
    session.add(owner)
    session.commit()
    event = Event(
        slug="vote-integrity",
        name="Vote Integrity",
        start_at=utcnow() - timedelta(days=3),
        end_at=utcnow() + timedelta(days=1),
        created_by_id=owner.id,
        voting_enabled=True,
        **rules,
    )
    session.add(event)
    session.commit()
    team = Team(event_id=event.id, name="T")
    session.add(team)
    session.commit()
    sub = Submission(team_id=team.id, event_id=event.id, title="S", description="d", status=SubmissionStatus.submitted)
    session.add(sub)
    session.commit()
    return event, sub


def test_rules_are_off_by_default(client, session):
    _, sub = _voting_event(session)
    _login_as(client, session, "vi-new@example.com")
    assert client.post(f"/api/submissions/{sub.id}/vote").status_code in (200, 201)


def test_unverified_account_is_refused_when_the_event_requires_verification(client, session):
    _, sub = _voting_event(session, voting_requires_verified=True)
    user = _login_as(client, session, "vi-unverified@example.com")
    r = client.post(f"/api/submissions/{sub.id}/vote")
    assert r.status_code == 403 and "Verify your email" in r.text

    user.email_verified_at = utcnow()
    session.add(user)
    session.commit()
    assert client.post(f"/api/submissions/{sub.id}/vote").status_code in (200, 201)


def test_accounts_made_after_the_cutoff_cannot_vote(client, session):
    _, sub = _voting_event(session, voting_account_cutoff=utcnow() - timedelta(minutes=5))
    _login_as(client, session, "vi-late@example.com")
    r = client.post(f"/api/submissions/{sub.id}/vote")
    assert r.status_code == 403 and "cutoff" in r.text


def test_verification_link_round_trip(client, session, mail_on):
    user = _login_as(client, session, "vi-verify@example.com")
    r = client.post("/api/auth/verify-email")
    assert r.status_code == 200, r.text
    assert "/api/auth/verify-email/confirm?token=" in mail_on[0][1]

    token = _verify_link.dumps({"u": user.id, "m": user.email})
    r = client.get(f"/api/auth/verify-email/confirm?token={token}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("verified=1")
    session.refresh(user)
    assert user.email_verified_at is not None
    assert client.get("/api/auth/me").json()["email_verified"] is True

    bad = client.get("/api/auth/verify-email/confirm?token=forged", follow_redirects=False)
    assert bad.headers["location"].endswith("verified=0")


def test_requiring_verification_is_refused_while_email_is_off(client, session, monkeypatch):
    monkeypatch.setattr(mailer, "CONFIG", mailer.MailConfig("", 587, "starttls", "", "", "HackFlow <x@y>"))
    event, _ = _voting_event(session)
    _login_as(client, session, "vi-org@example.com", Role.organizer)
    assert client.patch(f"/api/events/{event.id}", json={"voting_requires_verified": True}).status_code == 409
    # The cutoff needs no email, so it works on an offline install.
    cutoff = utcnow().isoformat()
    assert client.patch(f"/api/events/{event.id}", json={"voting_account_cutoff": cutoff}).status_code == 200


def test_organizer_sees_votes_sharing_a_client_and_can_void_them(client, session):
    event, sub = _voting_event(session)
    # The test client is one IP + user agent, so two accounts voting from it share a fingerprint.
    _login_as(client, session, "vi-sock1@example.com")
    client.post(f"/api/submissions/{sub.id}/vote")
    _login_as(client, session, "vi-sock2@example.com")
    client.post(f"/api/submissions/{sub.id}/vote")

    _login_as(client, session, "vi-org2@example.com", Role.participant)
    assert client.get(f"/api/events/{event.id}/votes/flagged").status_code == 403

    _login_as(client, session, "vi-org2@example.com", Role.organizer)
    flagged = client.get(f"/api/events/{event.id}/votes/flagged").json()
    assert len(flagged) == 2 and flagged[0]["voters_on_client"] == 2

    r = client.delete(f"/api/events/{event.id}/votes/{flagged[0]['vote_id']}")
    assert r.status_code == 204
    assert len(session.exec(select(Vote).where(Vote.submission_id == sub.id)).all()) == 1
    assert session.exec(select(AuditLog).where(AuditLog.action == "vote.voided")).first()
