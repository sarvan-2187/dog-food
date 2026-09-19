"""Phase 9: password recovery - revocable sessions, emailed reset links,
organizer-issued links, the admin email card, the break-glass CLI, and
changing a password while signed in."""
from datetime import timedelta
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app.audit.models import AuditLog
from app.auth import mailer
from app.auth.models import PasswordReset, Role, User
from app.auth.security import hash_password, verify_password
from app.timeutil import utcnow

PASSWORD = "supersecret1"
NEW_PASSWORD = "brand-new-pass"


def _user(session, email: str, role: Role = Role.participant) -> User:
    user = User(email=email, name=f"{email.split('@')[0].title()} Tester", role=role, password_hash=hash_password(PASSWORD))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _login(client, email: str) -> None:
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text


class FakeSMTP:
    """Stands in for smtplib.SMTP and records every message it is handed."""

    sent: list[EmailMessage] = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        pass

    def login(self, username, password):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture()
def mail_on(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(
        mailer,
        "CONFIG",
        mailer.MailConfig(host="smtp.test", port=587, security="starttls", username="", password="", sender="HackFlow <hf@test>"),
    )
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    return FakeSMTP.sent


@pytest.fixture()
def mail_off(monkeypatch):
    """Email off, and any attempt to open an SMTP connection fails the test -
    the section 1 guarantee: no config, no network call."""

    def refuse(*a, **k):
        raise AssertionError("an SMTP connection was attempted with email off")

    monkeypatch.setattr(mailer, "CONFIG", mailer.MailConfig("", 587, "starttls", "", "", "HackFlow <x@y>"))
    monkeypatch.setattr(mailer.smtplib, "SMTP", refuse)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", refuse)


def _link_from(msg: EmailMessage) -> str:
    text = msg.get_body(preferencelist=("plain",)).get_content()
    return next(line.strip() for line in text.splitlines() if "/reset/" in line)


def _token(link: str) -> str:
    return link.rsplit("/reset/", 1)[1]


class _Bound:
    """Run the CLI on the test's own transaction instead of a new connection."""

    session = None

    def __init__(self, *_a, **_k):
        pass

    def __enter__(self):
        return _Bound.session

    def __exit__(self, *exc):
        return False


# ---------------------------------------------------------------------------
# 9.1 - sessions are revocable
# ---------------------------------------------------------------------------

def test_a_cookie_signed_before_phase_9_still_works(client, session):
    """No "v" in the payload reads as version 0, so upgrading signs nobody out."""
    from app.auth.session import SESSION_COOKIE_NAME, _serializer

    user = _user(session, "legacy@example.com")
    client.cookies.set(SESSION_COOKIE_NAME, _serializer.dumps({"user_id": user.id}))
    assert client.get("/api/auth/me").status_code == 200


def test_changing_the_password_signs_out_every_other_session(client, session, mail_off):
    from app.main import app

    _user(session, "twodevices@example.com")
    _login(client, "twodevices@example.com")
    with TestClient(app) as laptop:
        laptop.post("/api/auth/login", json={"email": "twodevices@example.com", "password": PASSWORD})
        assert laptop.get("/api/auth/me").status_code == 200

        r = client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
        assert r.status_code == 200, r.text

        assert laptop.get("/api/auth/me").status_code == 401  # the other device is out
    assert client.get("/api/auth/me").status_code == 200  # this one got a fresh cookie


# ---------------------------------------------------------------------------
# 9.2 - emailed reset links
# ---------------------------------------------------------------------------

def test_forgot_password_emails_a_working_link_and_no_password(client, session, mail_on):
    user = _user(session, "forgetful@example.com")
    r = client.post("/api/auth/forgot-password", json={"email": user.email})
    assert r.status_code == 200

    assert len(mail_on) == 1
    msg = mail_on[0]
    assert msg["To"] == user.email
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert PASSWORD not in body
    link = _link_from(msg)

    preview = client.get(f"/api/password-resets/{_token(link)}/preview").json()
    assert preview == {"valid": True, "reason": "", "first_name": "Forgetful", "email_enabled": True}

    r = client.post(f"/api/password-resets/{_token(link)}/redeem", json={"new_password": NEW_PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == user.email
    assert client.get("/api/auth/me").status_code == 200  # signed straight in
    session.refresh(user)
    assert verify_password(NEW_PASSWORD, user.password_hash)
    # ...and the "your password was changed" notice went out too.
    assert [m["Subject"] for m in mail_on] == ["Reset your HackFlow password", "Your HackFlow password was changed"]


def test_forgot_password_answers_identically_for_unknown_addresses(client, session, mail_on):
    _user(session, "known@example.com")
    known = client.post("/api/auth/forgot-password", json={"email": "known@example.com"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert (known.status_code, known.json()) == (unknown.status_code, unknown.json())
    assert len(mail_on) == 1  # only the real account got mail


def test_the_rate_limit_still_answers_generically(client, session, mail_on):
    _user(session, "spammed@example.com")
    bodies = {
        client.post("/api/auth/forgot-password", json={"email": "spammed@example.com"}).text for _ in range(5)
    }
    assert len(bodies) == 1  # over the limit looks exactly like under it
    assert len(mail_on) == 3  # 3 per address per hour


def test_the_token_is_stored_only_as_a_hash(client, session, mail_on):
    user = _user(session, "hashed@example.com")
    client.post("/api/auth/forgot-password", json={"email": user.email})
    token = _token(_link_from(mail_on[0]))
    row = session.exec(select(PasswordReset).where(PasswordReset.user_id == user.id)).one()
    assert token not in row.token_hash
    assert len(row.token_hash) == 64


def test_preview_never_consumes_the_link(client, session, mail_on):
    """Mail scanners open links to check them; the person must still be able to use it."""
    user = _user(session, "scanned@example.com")
    client.post("/api/auth/forgot-password", json={"email": user.email})
    token = _token(_link_from(mail_on[0]))
    for _ in range(3):
        assert client.get(f"/api/password-resets/{token}/preview").json()["valid"] is True
    assert client.post(f"/api/password-resets/{token}/redeem", json={"new_password": NEW_PASSWORD}).status_code == 200


def test_a_link_works_once(client, session, mail_on):
    user = _user(session, "once@example.com")
    client.post("/api/auth/forgot-password", json={"email": user.email})
    token = _token(_link_from(mail_on[0]))
    assert client.post(f"/api/password-resets/{token}/redeem", json={"new_password": NEW_PASSWORD}).status_code == 200
    again = client.post(f"/api/password-resets/{token}/redeem", json={"new_password": "another-pass-1"})
    assert again.status_code == 410
    assert "already been used" in again.json()["detail"]
    assert client.get(f"/api/password-resets/{token}/preview").json()["reason"] == "used"


def test_an_expired_link_is_refused(client, session, mail_on):
    user = _user(session, "late@example.com")
    client.post("/api/auth/forgot-password", json={"email": user.email})
    token = _token(_link_from(mail_on[0]))
    row = session.exec(select(PasswordReset).where(PasswordReset.user_id == user.id)).one()
    row.expires_at = utcnow() - timedelta(seconds=1)
    session.add(row)
    session.commit()
    assert client.get(f"/api/password-resets/{token}/preview").json()["reason"] == "expired"
    assert client.post(f"/api/password-resets/{token}/redeem", json={"new_password": NEW_PASSWORD}).status_code == 410


def test_a_newer_link_retires_the_older_one(client, session, mail_on):
    user = _user(session, "twice@example.com")
    client.post("/api/auth/forgot-password", json={"email": user.email})
    client.post("/api/auth/forgot-password", json={"email": user.email})
    first, second = (_token(_link_from(m)) for m in mail_on[:2])
    assert client.get(f"/api/password-resets/{first}/preview").json()["valid"] is False
    assert client.post(f"/api/password-resets/{second}/redeem", json={"new_password": NEW_PASSWORD}).status_code == 200


def test_an_unknown_token_is_refused(client):
    assert client.get("/api/password-resets/not-a-real-token/preview").json()["reason"] == "unknown"
    r = client.post("/api/password-resets/not-a-real-token/redeem", json={"new_password": NEW_PASSWORD})
    assert r.status_code == 410


def test_a_reset_signs_out_an_existing_session(client, session, mail_on):
    from app.main import app

    user = _user(session, "stolen@example.com")
    with TestClient(app) as attacker:
        attacker.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
        assert attacker.get("/api/auth/me").status_code == 200
        client.post("/api/auth/forgot-password", json={"email": user.email})
        token = _token(_link_from(mail_on[0]))
        client.post(f"/api/password-resets/{token}/redeem", json={"new_password": NEW_PASSWORD})
        assert attacker.get("/api/auth/me").status_code == 401


def test_the_new_password_follows_the_signup_rule(client, session, mail_on):
    user = _user(session, "short@example.com")
    client.post("/api/auth/forgot-password", json={"email": user.email})
    token = _token(_link_from(mail_on[0]))
    assert client.post(f"/api/password-resets/{token}/redeem", json={"new_password": "short"}).status_code == 422
    assert client.get(f"/api/password-resets/{token}/preview").json()["valid"] is True  # still usable


def test_with_email_off_forgot_password_says_so_and_opens_no_connection(client, session, mail_off):
    _user(session, "offline@example.com")
    assert client.get("/api/auth/recovery-options").json() == {"email": False}
    r = client.post("/api/auth/forgot-password", json={"email": "offline@example.com"})
    assert r.status_code == 503
    assert "organizer" in r.json()["detail"]


def test_issuing_and_redeeming_are_audited(client, session, mail_on):
    user = _user(session, "audited@example.com")
    client.post("/api/auth/forgot-password", json={"email": user.email})
    client.post(f"/api/password-resets/{_token(_link_from(mail_on[0]))}/redeem", json={"new_password": NEW_PASSWORD})
    actions = [
        a.action
        for a in session.exec(select(AuditLog).where(AuditLog.entity_type == "user", AuditLog.entity_id == user.id))
    ]
    assert "password_reset.issued" in actions
    assert "password_reset.redeemed" in actions


# ---------------------------------------------------------------------------
# 9.4 - organizer-issued links and who may reset whom
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("issuer_role", "target_role", "allowed"),
    [
        (Role.organizer, Role.participant, True),
        (Role.organizer, Role.judge, True),
        (Role.organizer, Role.organizer, False),
        (Role.organizer, Role.admin, False),
        (Role.admin, Role.participant, True),
        (Role.admin, Role.judge, True),
        (Role.admin, Role.organizer, True),
        (Role.admin, Role.admin, False),
        (Role.participant, Role.participant, False),
        (Role.judge, Role.participant, False),
    ],
)
def test_who_may_reset_whom(client, session, mail_off, issuer_role, target_role, allowed):
    issuer = _user(session, f"issuer-{issuer_role.value}@example.com", issuer_role)
    target = _user(session, f"target-{target_role.value}@example.com", target_role)
    _login(client, issuer.email)
    r = client.post("/api/password-resets", json={"email": target.email})
    assert r.status_code == (201 if allowed else 403), r.text


def test_an_organizer_link_redeems_and_names_who_issued_it(client, session, mail_off):
    organizer = _user(session, "help-desk@example.com", Role.organizer)
    participant = _user(session, "locked-out@example.com")
    _login(client, organizer.email)
    issued = client.post("/api/password-resets", json={"email": participant.email}).json()
    assert issued["url"].startswith("http://localhost:8000/reset/")
    client.post("/api/auth/logout")

    r = client.post(f"/api/password-resets/{_token(issued['url'])}/redeem", json={"new_password": NEW_PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json()["issued_by_name"] == organizer.name


def test_nobody_issues_a_link_for_themselves(client, session, mail_off):
    admin = _user(session, "self-admin@example.com", Role.admin)
    _login(client, admin.email)
    r = client.post("/api/password-resets", json={"email": admin.email})
    assert r.status_code == 403
    assert "profile" in r.json()["detail"]


def test_an_unknown_email_is_a_plain_404_for_organizers(client, session, mail_off):
    organizer = _user(session, "lookup@example.com", Role.organizer)
    _login(client, organizer.email)
    r = client.post("/api/password-resets", json={"email": "ghost@example.com"})
    assert r.status_code == 404


def test_organizer_issuing_is_rate_limited(client, session, mail_off):
    organizer = _user(session, "busy-desk@example.com", Role.organizer)
    participant = _user(session, "again-and-again@example.com")
    _login(client, organizer.email)
    # Refusals don't count against the limit...
    for _ in range(5):
        assert client.post("/api/password-resets", json={"email": "ghost@example.com"}).status_code == 404
    # ...issued links do: 30 an hour.
    codes = [client.post("/api/password-resets", json={"email": participant.email}).status_code for _ in range(31)]
    assert codes[:30] == [201] * 30
    assert codes[30] == 429


# ---------------------------------------------------------------------------
# 9.3 - admin email card
# ---------------------------------------------------------------------------

def test_email_status_is_admin_only_and_never_returns_the_password(client, session, monkeypatch):
    monkeypatch.setattr(
        mailer, "CONFIG", mailer.MailConfig("smtp.test", 587, "starttls", "hf@test", "hunter2-secret", "HackFlow <hf@test>")
    )
    organizer = _user(session, "not-admin@example.com", Role.organizer)
    _login(client, organizer.email)
    assert client.get("/api/admin/email").status_code == 403

    admin = _user(session, "mail-admin@example.com", Role.admin)
    _login(client, admin.email)
    r = client.get("/api/admin/email")
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert r.json()["username_set"] is True
    assert "hunter2-secret" not in r.text


def test_the_test_email_reaches_the_admin(client, session, mail_on):
    admin = _user(session, "tester-admin@example.com", Role.admin)
    _login(client, admin.email)
    r = client.post("/api/admin/email/test")
    assert r.status_code == 200, r.text
    assert r.json() == {"sent_to": admin.email}
    assert mail_on[-1]["To"] == admin.email


def test_a_failed_test_email_explains_itself(client, session, monkeypatch):
    import smtplib

    class RejectingSMTP(FakeSMTP):
        def login(self, username, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(
        mailer, "CONFIG", mailer.MailConfig("smtp.test", 587, "starttls", "hf@test", "wrong", "HackFlow <hf@test>")
    )
    monkeypatch.setattr(mailer.smtplib, "SMTP", RejectingSMTP)
    admin = _user(session, "unlucky-admin@example.com", Role.admin)
    _login(client, admin.email)
    r = client.post("/api/admin/email/test")
    assert r.status_code == 502
    assert "app password" in r.json()["detail"]


# ---------------------------------------------------------------------------
# 9.6 - break-glass CLI
# ---------------------------------------------------------------------------

def test_the_cli_prints_a_working_link_even_for_an_admin(client, session, monkeypatch, capsys):
    from app.auth import reset_link

    admin = _user(session, "locked-admin@example.com", Role.admin)
    _Bound.session = session
    monkeypatch.setattr(reset_link, "Session", _Bound)
    assert reset_link.main([admin.email]) == 0
    url = capsys.readouterr().out.strip().splitlines()[-1]
    r = client.post(f"/api/password-resets/{_token(url)}/redeem", json={"new_password": NEW_PASSWORD})
    assert r.status_code == 200, r.text


def test_the_cli_refuses_an_unknown_email(monkeypatch, session):
    from app.auth import reset_link

    _Bound.session = session
    monkeypatch.setattr(reset_link, "Session", _Bound)
    assert reset_link.main(["nobody-at-all@example.com"]) == 1


# ---------------------------------------------------------------------------
# 9.5 - change password while signed in
# ---------------------------------------------------------------------------

def test_a_wrong_current_password_is_refused_inline(client, session, mail_off):
    user = _user(session, "fumble@example.com")
    _login(client, user.email)
    r = client.post("/api/auth/password", json={"current_password": "not-it-at-all", "new_password": NEW_PASSWORD})
    assert r.status_code == 400
    assert r.json()["detail"] == "Your current password is incorrect."
    session.refresh(user)
    assert verify_password(PASSWORD, user.password_hash)


def test_the_new_password_is_used_from_then_on(client, session, mail_off):
    user = _user(session, "rotate@example.com")
    _login(client, user.email)
    r = client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert r.status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD}).status_code == 401
    assert client.post("/api/auth/login", json={"email": user.email, "password": NEW_PASSWORD}).status_code == 200


def test_a_change_sends_the_changed_notice_when_mail_is_on(client, session, mail_on):
    user = _user(session, "notified@example.com")
    _login(client, user.email)
    client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert [m["Subject"] for m in mail_on] == ["Your HackFlow password was changed"]
    assert mail_on[0]["To"] == user.email


def test_signed_out_users_cannot_change_a_password(client):
    r = client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert r.status_code == 401
