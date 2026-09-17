"""Idempotent fixture seeding, run automatically on app startup.

Ordered pipeline (users -> events -> teams -> submissions -> rubrics) because
each step needs the previous step's generated ids. Every insert is guarded by a lookup
on the row's natural key, so re-running on an already-seeded database is a
no-op.
"""
import json
import logging
import os
from pathlib import Path

from datetime import datetime

from sqlmodel import Session, select

from .db import engine
from .timeutil import ensure_utc

log = logging.getLogger("seed")

FIXTURES_DIR = Path(os.getenv("FIXTURES_DIR", "fixtures"))


def load_fixture(name: str) -> list[dict]:
    """Read fixtures/<name>. Returns [] when the file is absent."""
    path = FIXTURES_DIR / name
    if not path.exists():
        log.warning("fixture %s not found, skipping", path)
        return []
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _fixture_dt(value: str) -> datetime:
    """Fixture timestamps are written without an offset and mean UTC. Parse them
    explicitly so they never get read as the container's local time."""
    return ensure_utc(datetime.fromisoformat(value))


def _seed_users(session: Session) -> dict[str, int]:
    from .auth.models import Role, User
    from .auth.security import hash_password

    email_to_id: dict[str, int] = {}
    for row in load_fixture("users.json"):
        existing = session.exec(select(User).where(User.email == row["email"])).first()
        if existing:
            email_to_id[row["email"]] = existing.id
            continue
        user = User(
            email=row["email"],
            name=row["name"],
            role=Role(row["role"]),
            password_hash=hash_password(row["password"]),
        )
        session.add(user)
        session.flush()
        email_to_id[row["email"]] = user.id
    return email_to_id


def _seed_events(session: Session, email_to_id: dict[str, int]) -> dict[str, int]:
    from .events.models import Event

    slug_to_id: dict[str, int] = {}
    for row in load_fixture("events.json"):
        existing = session.exec(select(Event).where(Event.slug == row["slug"])).first()
        if existing:
            slug_to_id[row["slug"]] = existing.id
            continue
        event = Event(
            slug=row["slug"],
            name=row["name"],
            description=row.get("description", ""),
            start_at=_fixture_dt(row["start_at"]),
            end_at=_fixture_dt(row["end_at"]),
            tracks=row.get("tracks", []),
            created_by_id=email_to_id[row["created_by"]],
        )
        session.add(event)
        session.flush()
        slug_to_id[row["slug"]] = event.id
    return slug_to_id


def _seed_teams(session: Session, email_to_id: dict[str, int], slug_to_id: dict[str, int]) -> dict[str, int]:
    from .teams.models import Team, TeamMembership

    name_to_id: dict[str, int] = {}
    for row in load_fixture("teams.json"):
        event_id = slug_to_id[row["event_slug"]]
        existing = session.exec(select(Team).where(Team.name == row["name"], Team.event_id == event_id)).first()
        if existing:
            name_to_id[row["name"]] = existing.id
            continue
        team = Team(name=row["name"], event_id=event_id)
        session.add(team)
        session.flush()
        for email in row.get("member_emails", []):
            session.add(TeamMembership(team_id=team.id, user_id=email_to_id[email]))
        name_to_id[row["name"]] = team.id
    return name_to_id


def _seed_submissions(session: Session, slug_to_id: dict[str, int], name_to_id: dict[str, int]) -> None:
    from .submissions.models import Submission, SubmissionStatus

    for row in load_fixture("submissions.json"):
        team_id = name_to_id[row["team_name"]]
        existing = session.exec(select(Submission).where(Submission.team_id == team_id)).first()
        if existing:
            continue
        session.add(
            Submission(
                team_id=team_id,
                event_id=slug_to_id[row["event_slug"]],
                title=row.get("title", ""),
                description=row.get("description", ""),
                track=row.get("track", ""),
                status=SubmissionStatus(row.get("status", "draft")),
            )
        )


def _seed_rubrics(session: Session, slug_to_id: dict[str, int]) -> None:
    from .judging.models import Rubric

    for row in load_fixture("rubrics.json"):
        event_id = slug_to_id[row["event_slug"]]
        if session.exec(select(Rubric).where(Rubric.event_id == event_id)).first():
            continue
        session.add(Rubric(event_id=event_id, name=row["name"], criteria=row["criteria"]))


def run_seed() -> None:
    with Session(engine) as session:
        email_to_id = _seed_users(session)
        slug_to_id = _seed_events(session, email_to_id)
        name_to_id = _seed_teams(session, email_to_id, slug_to_id)
        _seed_submissions(session, slug_to_id, name_to_id)
        _seed_rubrics(session, slug_to_id)
        session.commit()
    log.info("seeding complete")


def _self_check() -> None:
    """Smallest check that fails if the fixture-loading contract breaks.

    Run with: python -m app.seed  (from api/)
    """
    from datetime import timezone

    assert load_fixture("__definitely_missing__.json") == []
    parsed = _fixture_dt("2026-09-21T18:00:00")
    assert parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0, parsed
    assert _fixture_dt("2026-09-21T18:00:00+05:30").astimezone(timezone.utc).hour == 12
    print("seed self-check ok")


if __name__ == "__main__":
    _self_check()
