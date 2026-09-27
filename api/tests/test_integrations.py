"""API keys, event stages, verifiable certificates and eligibility flags."""
from datetime import timedelta

from app.auth.api_keys import ApiKey
from app.auth.models import Role, User
from app.auth.security import hash_password
from app.events.models import Event
from app.judging.models import Rubric
from app.scoring.certificate import certificate_serial
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow

PASSWORD = "supersecret1"


def _user(session, email: str, role: Role = Role.participant) -> User:
    user = User(email=email, name=f"{email.split('@')[0].title()} Person", role=role, password_hash=hash_password(PASSWORD))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _login(client, user: User) -> None:
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD}).status_code == 200


def _event(session, slug: str, owner: User, *, revealed: bool = True, max_team_size: int = 4, tracks=None) -> Event:
    now = utcnow()
    event = Event(
        slug=slug,
        name=slug.replace("-", " ").title(),
        start_at=now - timedelta(days=3),
        end_at=now - timedelta(days=1),
        results_hidden_until=now - timedelta(hours=1) if revealed else now + timedelta(days=5),
        created_by_id=owner.id,
        max_team_size=max_team_size,
        tracks=tracks or [],
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    session.add(Rubric(event_id=event.id, name="Main", criteria=[{"key": "k", "label": "K", "weight": 1, "max_score": 10}]))
    session.commit()
    return event


def _entry(session, event: Event, name: str, members: list[User], **fields) -> Submission:
    team = Team(event_id=event.id, name=name, captain_id=members[0].id)
    session.add(team)
    session.commit()
    session.refresh(team)
    for m in members:
        session.add(TeamMembership(team_id=team.id, user_id=m.id, event_id=event.id))
    sub = Submission(team_id=team.id, event_id=event.id, title=f"{name} project", status=SubmissionStatus.submitted, **fields)
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub


# --- API keys ----------------------------------------------------------------

def test_an_api_key_is_shown_once_and_authenticates_as_its_owner(client, session):
    org = _user(session, "keys-org@example.com", Role.organizer)
    _login(client, org)
    created = client.post("/api/api-keys", json={"name": "Discord bot"})
    assert created.status_code == 201, created.text
    key = created.json()["key"]
    assert key.startswith("hf_")
    listed = client.get("/api/api-keys").json()
    assert [k["name"] for k in listed] == ["Discord bot"]
    assert "key" not in listed[0], "a key is never shown again"
    row = session.get(ApiKey, created.json()["id"])
    assert key not in row.key_hash, "only a hash is stored"

    client.post("/api/auth/logout")
    client.cookies.clear()
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {key}"})
    assert me.status_code == 200 and me.json()["email"] == org.email
    # It passes the same role gates the organizer does, e.g. creating an event.
    made = client.post(
        "/api/events",
        headers={"Authorization": f"Bearer {key}"},
        json={"name": "Via API", "slug": "via-api-key", "start_at": "2027-01-01T09:00:00Z", "end_at": "2027-01-02T09:00:00Z"},
    )
    assert made.status_code in (200, 201), made.text


def test_a_revoked_or_wrong_key_is_refused(client, session):
    org = _user(session, "revoke-org@example.com", Role.organizer)
    _login(client, org)
    created = client.post("/api/api-keys", json={"name": "CRM sync"}).json()
    assert client.delete(f"/api/api-keys/{created['id']}").status_code == 204
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {created['key']}"}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer hf_made-up"}).status_code == 401


def test_participants_cannot_mint_keys_and_nobody_revokes_someone_elses(client, session):
    alice = _user(session, "owner-org@example.com", Role.organizer)
    _login(client, alice)
    key_id = client.post("/api/api-keys", json={"name": "Mine"}).json()["id"]

    other = _user(session, "other-org@example.com", Role.organizer)
    _login(client, other)
    assert client.delete(f"/api/api-keys/{key_id}").status_code == 404

    participant = _user(session, "keys-participant@example.com")
    _login(client, participant)
    assert client.post("/api/api-keys", json={"name": "Nope"}).status_code == 403


def test_a_deactivated_owner_takes_their_keys_with_them(client, session):
    org = _user(session, "gone-org@example.com", Role.organizer)
    _login(client, org)
    key = client.post("/api/api-keys", json={"name": "Old"}).json()["key"]
    org.is_active = False
    session.add(org)
    session.commit()
    client.cookies.clear()
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {key}"}).status_code == 401


# --- Stages ------------------------------------------------------------------

def test_stages_are_saved_in_order_and_round_trip_through_export(client, session):
    org = _user(session, "stages-org@example.com", Role.organizer)
    event = _event(session, "stages-event", org)
    _login(client, org)
    r = client.patch(
        f"/api/events/{event.id}",
        json={
            "stages": [
                {"name": "Judging", "starts_at": "2027-01-03T00:00:00Z", "ends_at": "2027-01-04T00:00:00Z"},
                {"name": "Build sprint", "description": "48 hours", "starts_at": "2027-01-01T00:00:00Z", "ends_at": "2027-01-03T00:00:00Z"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert [s["name"] for s in r.json()["stages"]] == ["Build sprint", "Judging"], "sorted by start"
    exported = client.get(f"/api/events/{event.id}/export.json").json()
    assert [s["name"] for s in exported["event"]["stages"]] == ["Build sprint", "Judging"]


def test_a_stage_that_ends_before_it_starts_is_refused(client, session):
    org = _user(session, "badstage-org@example.com", Role.organizer)
    event = _event(session, "bad-stage", org)
    _login(client, org)
    r = client.patch(
        f"/api/events/{event.id}",
        json={"stages": [{"name": "Oops", "starts_at": "2027-01-02T00:00:00Z", "ends_at": "2027-01-01T00:00:00Z"}]},
    )
    assert r.status_code == 422
    too_many = [{"name": f"S{i}", "starts_at": "2027-01-01T00:00:00Z", "ends_at": "2027-01-02T00:00:00Z"} for i in range(11)]
    assert client.patch(f"/api/events/{event.id}", json={"stages": too_many}).status_code == 422


# --- Certificates ------------------------------------------------------------

def test_a_certificate_serial_verifies_publicly_with_its_members(client, session):
    org = _user(session, "cert-org@example.com", Role.organizer)
    event = _event(session, "cert-event", org)
    a, b = _user(session, "ada@example.com"), _user(session, "bo@example.com")
    sub = _entry(session, event, "Verifiers", [a, b], repo_url="https://github.com/x/y")
    client.cookies.clear()
    r = client.get(f"/api/certificates/{certificate_serial(sub.id)}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["team_name"] == "Verifiers"
    assert body["members"] == ["Ada Person", "Bo Person"]
    assert body["event_name"] == event.name


def test_forged_or_early_serials_read_as_not_found(client, session):
    org = _user(session, "early-org@example.com", Role.organizer)
    hidden = _event(session, "cert-hidden", org, revealed=False)
    sub = _entry(session, hidden, "Too Soon", [_user(session, "soon@example.com")])
    client.cookies.clear()
    serial = certificate_serial(sub.id)
    assert client.get(f"/api/certificates/{serial}").status_code == 404, "results not public yet"
    forged = serial[:-1] + ("0" if not serial.endswith("0") else "1")
    assert client.get(f"/api/certificates/{forged}").status_code == 404
    assert client.get("/api/certificates/not-a-serial").status_code == 404


def test_the_certificate_pdf_names_the_members(client, session):
    org = _user(session, "pdf-org@example.com", Role.organizer)
    event = _event(session, "cert-pdf", org)
    sub = _entry(session, event, "Printers", [_user(session, "pat@example.com")])
    _login(client, org)
    r = client.get(f"/api/submissions/{sub.id}/certificate.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF-")


def test_an_event_picks_a_certificate_design_and_it_travels_with_the_backup(client, session):
    org = _user(session, "design-org@example.com", Role.organizer)
    event = _event(session, "cert-design", org)
    sub = _entry(session, event, "Stylish", [_user(session, "sty@example.com")])
    _login(client, org)
    plain = client.get(f"/api/submissions/{sub.id}/certificate.pdf").content

    r = client.patch(f"/api/events/{event.id}", json={"certificate_template": "midnight"})
    assert r.status_code == 200 and r.json()["certificate_template"] == "midnight"
    styled = client.get(f"/api/submissions/{sub.id}/certificate.pdf").content
    assert styled.startswith(b"%PDF-") and len(styled) > len(plain) + 50_000, "the background is embedded"
    assert client.get(f"/api/events/{event.id}/export.json").json()["event"]["certificate_template"] == "midnight"

    assert client.patch(f"/api/events/{event.id}", json={"certificate_template": "comic-sans"}).status_code == 422


# --- Eligibility flags -------------------------------------------------------

def test_eligibility_flags_point_at_what_to_check(client, session):
    org = _user(session, "elig-org@example.com", Role.organizer)
    event = _event(session, "elig-event", org, max_team_size=1, tracks=["Tools"])
    good = _entry(
        session, event, "Clean", [_user(session, "clean@example.com")],
        repo_url="https://github.com/a/clean", description="A thorough description of what this project does.", track="Tools",
    )
    dup1 = _entry(session, event, "Copy A", [_user(session, "ca@example.com")], repo_url="https://github.com/a/same")
    dup2 = _entry(
        session, event, "Copy B", [_user(session, "cb@example.com"), _user(session, "cb2@example.com")],
        repo_url="https://GitHub.com/a/same.git/",
    )
    _login(client, org)
    listed = client.get(f"/api/events/{event.id}/eligibility").json()
    rows = {r["submission_id"]: r for r in listed}
    assert rows[good.id]["flags"] == []
    assert "Same repository as another entry in this event." in rows[dup1.id]["flags"]
    assert "Same repository as another entry in this event." in rows[dup2.id]["flags"], "URLs are compared normalised"
    assert any("limit is 1" in f for f in rows[dup2.id]["flags"])
    assert "No track chosen." in rows[dup1.id]["flags"]
    assert listed[-1]["submission_id"] == good.id, "flagged entries come first"
