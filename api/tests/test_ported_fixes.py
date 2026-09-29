"""Fixes ported from PR #15 onto main's hardening: static files outside the
per-client allowance, the legacy image route frozen at the deadline, tracks
checked, draft rubrics hidden, webhooks capped with a test ping, rubric scale in
the weighted total, and per-row completeness in the results."""
from datetime import timedelta

import pytest
from sqlmodel import select

from app import request_limit
from app.auth.models import Role, User
from app.auth.security import hash_password
from app.auth.session import create_session_token
from app.crypto import verify_record
from app.events.models import Event
from app.judging.models import Rubric
from app.scoring.normalization import normalized_table
from app.scoring.router import _weighted_total
from app.submissions.models import Submission
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _user(session, email: str, role: Role = Role.participant) -> User:
    user = User(email=email, name=email.split("@")[0], role=role, password_hash=hash_password("supersecret1"))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _sign_in(client, user: User) -> None:
    client.cookies.set("session", create_session_token(user.id, user.session_version))


def _event(session, owner: User, slug: str, *, open_=True, tracks=None, status="published") -> Event:
    now = utcnow()
    event = Event(
        slug=slug, name=slug, tracks=tracks or [], status=status,
        start_at=now - timedelta(days=2),
        end_at=now + timedelta(days=1) if open_ else now - timedelta(hours=1),
        created_by_id=owner.id,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def _team(session, event: Event, member: User) -> Team:
    team = Team(event_id=event.id, name=f"team-{event.slug}", captain_id=member.id)
    session.add(team)
    session.commit()
    session.add(TeamMembership(team_id=team.id, user_id=member.id))
    session.commit()
    return team


# --- static files and the per-client allowance --------------------------------

def test_static_files_do_not_spend_the_per_client_allowance(client, monkeypatch):
    """A page view fetches a dozen files; with them charged, a venue of
    anonymous visitors behind one NAT address ran dry within a minute."""
    monkeypatch.setattr(request_limit.client_limiter, "limit", 3)
    for path in ("/favicon.ico", "/fonts/satoshi-400.woff2", "/assets/index.js", "/images/raptor.png",
                 "/media/x.png") * 3:
        assert client.get(path).status_code != 429, path
    for _ in range(3):
        assert client.get("/api/gallery").status_code != 429, "API budget untouched by the files"
    assert client.get("/api/gallery").status_code == 429


def test_static_files_still_count_towards_the_per_ip_ceiling(client, monkeypatch):
    monkeypatch.setattr(request_limit.ip_limiter, "limit", 4)
    codes = [client.get("/favicon.ico").status_code for _ in range(5)]
    assert codes[:4].count(429) == 0 and codes[4] == 429


# --- submissions ----------------------------------------------------------------

def test_the_legacy_image_upload_is_frozen_after_the_deadline(client, session):
    member = _user(session, "legacy-img@example.com")
    event = _event(session, member, "legacy-img", open_=False)
    team = _team(session, event, member)
    session.add(Submission(team_id=team.id, event_id=event.id, title="Late", description="x"))
    session.commit()
    _sign_in(client, member)
    r = client.post(f"/api/teams/{team.id}/submission/image", files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 400, r.text


def test_a_submission_track_must_be_one_of_the_events_tracks(client, session):
    member = _user(session, "track-check@example.com")
    event = _event(session, member, "track-check", tracks=["AI", "Web"])
    team = _team(session, event, member)
    _sign_in(client, member)
    assert client.patch(f"/api/teams/{team.id}/submission", json={"track": "Made Up"}).status_code == 422
    r = client.patch(f"/api/teams/{team.id}/submission", json={"track": "AI"})
    assert r.status_code == 200 and r.json()["track"] == "AI"


def test_a_draft_events_rubrics_are_hidden_from_participants(client, session):
    organizer = _user(session, "draft-rub-org@example.com", Role.organizer)
    event = _event(session, organizer, "draft-rubrics", status="draft")
    session.add(Rubric(event_id=event.id, name="Main", criteria=[{"key": "a", "label": "A", "weight": 1.0,
                                                                  "max_score": 10}]))
    session.commit()
    _sign_in(client, _user(session, "draft-rub-p@example.com"))
    assert client.get(f"/api/events/{event.id}/rubrics").status_code == 404
    _sign_in(client, organizer)
    assert client.get(f"/api/events/{event.id}/rubrics").status_code == 200


# --- webhooks -------------------------------------------------------------------

class _Ok:
    is_success = True


def test_webhooks_per_event_are_capped_and_deduplicated(client, session):
    organizer = _user(session, "wh-cap@example.com", Role.organizer)
    event = _event(session, organizer, "wh-cap")
    _sign_in(client, organizer)
    for i in range(10):
        r = client.post(f"/api/events/{event.id}/webhooks", json={"url": f"https://example.com/h{i}"})
        assert r.status_code == 201, r.text
    assert client.post(f"/api/events/{event.id}/webhooks", json={"url": "https://example.com/h0"}).status_code == 409
    assert client.post(f"/api/events/{event.id}/webhooks", json={"url": "https://example.com/h10"}).status_code == 409


def test_test_ping_sends_a_signed_webhook_test_delivery(client, session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.webhooks.service.httpx.post", lambda url, json, timeout, **_kw: (sent.append(json), _Ok())[1]
    )
    organizer = _user(session, "wh-ping@example.com", Role.organizer)
    event = _event(session, organizer, "wh-ping")
    _sign_in(client, organizer)
    hook = client.post(f"/api/events/{event.id}/webhooks", json={"url": "https://example.com/ping"}).json()
    r = client.post(f"/api/events/{event.id}/webhooks/{hook['id']}/test")
    assert r.status_code == 200 and r.json()["last_status"] == "delivered"
    body = sent[0]
    assert body["record"]["topic"] == "webhook.test" and body["record"]["delivery_id"]
    assert verify_record(body["record"], body["signature"], body["public_key"])


def test_test_ping_on_another_events_webhook_is_404(client, session):
    organizer = _user(session, "wh-ping404@example.com", Role.organizer)
    a, b = _event(session, organizer, "wh-a"), _event(session, organizer, "wh-b")
    _sign_in(client, organizer)
    hook = client.post(f"/api/events/{a.id}/webhooks", json={"url": "https://example.com/a"}).json()
    assert client.post(f"/api/events/{b.id}/webhooks/{hook['id']}/test").status_code == 404


# --- scoring --------------------------------------------------------------------

def test_weighted_total_respects_weights_across_different_max_scores():
    criteria = [
        {"key": "tech", "weight": 0.7, "max_score": 10},
        {"key": "pitch", "weight": 0.3, "max_score": 100},
    ]
    # Perfect tech with zero pitch must beat zero tech with perfect pitch: 70% vs 30%.
    assert _weighted_total(criteria, {"tech": 10, "pitch": 0}) == pytest.approx(70.0)
    assert _weighted_total(criteria, {"tech": 0, "pitch": 100}) == pytest.approx(30.0)


def test_weighted_total_is_unchanged_for_a_single_scale_rubric():
    criteria = [{"key": k, "weight": w, "max_score": 5} for k, w in (("a", 0.5), ("b", 0.25), ("c", 0.25))]
    assert _weighted_total(criteria, {"a": 4, "b": 3, "c": 5}) == pytest.approx(0.5 * 4 + 0.25 * 3 + 0.25 * 5)


def test_rows_say_how_many_judges_moved_the_score():
    rows = {r["submission_id"]: r for r in normalized_table({1: {101: 9.0, 102: 3.0}, 2: {101: 5.0}})}
    assert rows[101]["judges"] == 2 and rows[101]["informative_judges"] == 1
    assert rows[102]["informative_judges"] == 1


def test_an_import_with_a_zero_max_score_is_refused(client, session):
    organizer = _user(session, "imp-zero@example.com", Role.organizer)
    _sign_in(client, organizer)
    payload = {
        "slug": "imp-zero", "name": "Zero", "start_at": "2026-01-01T00:00:00+00:00",
        "end_at": "2026-01-02T00:00:00+00:00",
        "rubrics": [{"name": "Main", "criteria": [{"key": "a", "label": "A", "weight": 1.0, "max_score": 0}]}],
    }
    r = client.post("/api/events/import", json=payload)
    assert r.status_code == 422 and "positive" in r.text
    assert session.exec(select(Event).where(Event.slug == "imp-zero")).first() is None
