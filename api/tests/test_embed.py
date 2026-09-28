"""Embeddable gallery widget and the frame policy that protects everything else."""
from datetime import timedelta

from app.auth.models import Role, User
from app.events.models import Event
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team
from app.timeutil import utcnow


def _event(session, slug: str, status: str = "published") -> Event:
    owner = User(email=f"{slug}@example.com", name="Owner", role=Role.organizer, password_hash="x")
    session.add(owner)
    session.commit()
    event = Event(
        slug=slug,
        name="Embed <Hack>",
        start_at=utcnow() - timedelta(days=2),
        end_at=utcnow() + timedelta(days=1),
        created_by_id=owner.id,
        status=status,
    )
    session.add(event)
    session.commit()
    return event


def _submit(session, event: Event, title: str, status=SubmissionStatus.submitted) -> Submission:
    team = Team(event_id=event.id, name=f"Team {title}")
    session.add(team)
    session.commit()
    sub = Submission(team_id=team.id, event_id=event.id, title=title, description="desc", status=status)
    session.add(sub)
    session.commit()
    return sub


def test_widget_lists_submitted_projects_with_escaped_text(client, session):
    event = _event(session, "embed-ok")
    sub = _submit(session, event, '<script>alert("x")</script>')
    _submit(session, event, "Still a draft", SubmissionStatus.draft)

    r = client.get("/embed/events/embed-ok")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "<script>" not in r.text and "&lt;script&gt;" in r.text
    assert "Embed &lt;Hack&gt;" in r.text
    assert f'href="/submissions/{sub.id}"' in r.text
    assert "Still a draft" not in r.text


def test_draft_or_unknown_event_is_not_embeddable(client, session):
    _event(session, "embed-draft", status="draft")
    assert client.get("/embed/events/embed-draft").status_code == 404
    assert client.get("/embed/events/nope").status_code == 404


def test_only_the_widget_may_be_framed(client, session):
    _event(session, "embed-frame")
    widget = client.get("/embed/events/embed-frame")
    assert widget.headers["content-security-policy"] == "frame-ancestors *"
    assert "x-frame-options" not in widget.headers

    for path in ("/healthz", "/api/gallery"):
        r = client.get(path)
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["content-security-policy"] == "frame-ancestors 'none'"
