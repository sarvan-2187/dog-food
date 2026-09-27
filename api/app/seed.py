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

from datetime import datetime, timedelta

from sqlmodel import Session, select

from .db import engine
from .timeutil import ensure_utc, utcnow

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
            # Fixture accounts are vouched for by whoever loaded them.
            email_verified_at=utcnow(),
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
            prize_config=row.get("prize_config", {}),
            max_team_size=row.get("max_team_size", 4),
            cover_image_url=row.get("cover_image_url"),
            voting_enabled=row.get("voting_enabled", False),
            rules=row.get("rules", ""),
            results_hidden_until=(
                _fixture_dt(row["results_hidden_until"]) if row.get("results_hidden_until") else None
            ),
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
        members = row.get("member_emails", [])
        # Seeding runs after the boot-time backfills, so the captain is set here
        # rather than left for the next boot (PLAN.md 10.9).
        team = Team(name=row["name"], event_id=event_id, captain_id=email_to_id[members[0]] if members else None)
        session.add(team)
        session.flush()
        for email in members:
            session.add(TeamMembership(team_id=team.id, user_id=email_to_id[email]))
        name_to_id[row["name"]] = team.id
    return name_to_id


def _seed_submissions(session: Session, slug_to_id: dict[str, int], name_to_id: dict[str, int]) -> None:
    from .storage.models import StoredFile
    from .storage.service import checksum_of, storage
    from .submissions.models import Submission, SubmissionStatus

    for row in load_fixture("submissions.json"):
        team_id = name_to_id[row["team_name"]]
        existing = session.exec(select(Submission).where(Submission.team_id == team_id)).first()
        if existing:
            continue
        submission = Submission(
            team_id=team_id,
            event_id=slug_to_id[row["event_slug"]],
            title=row.get("title", ""),
            description=row.get("description", ""),
            track=row.get("track", ""),
            repo_url=row.get("repo_url", ""),
            demo_url=row.get("demo_url", ""),
            video_url=row.get("video_url", ""),
            status=SubmissionStatus(row.get("status", "draft")),
        )
        session.add(submission)
        image_name = row.get("image")
        if not image_name:
            continue
        session.flush()  # need submission.id before it can own a StoredFile
        image_path = FIXTURES_DIR / "images" / image_name
        if not image_path.exists():
            log.warning("seed image %s not found, skipping", image_path)
            continue
        data = image_path.read_bytes()
        key = storage.save(data, "image/png")
        session.add(
            StoredFile(
                key=key,
                owner_type="submission",
                owner_id=submission.id,
                content_type="image/png",
                size_bytes=len(data),
                checksum=checksum_of(data),
            )
        )


def _seed_rubrics(session: Session, slug_to_id: dict[str, int]) -> None:
    """An event may have several rubrics now, so idempotency is keyed on
    (event, name) rather than "this event already has a rubric" -- the old
    check would have skipped every rubric past the first on a re-run."""
    from .judging.models import Rubric

    for row in load_fixture("rubrics.json"):
        event_id = slug_to_id[row["event_slug"]]
        if session.exec(
            select(Rubric).where(Rubric.event_id == event_id, Rubric.name == row["name"])
        ).first():
            continue
        session.add(Rubric(event_id=event_id, name=row["name"], criteria=row["criteria"]))


def _seed_event_judges(session: Session, email_to_id: dict[str, int], slug_to_id: dict[str, int]) -> None:
    """PLAN.md 10.1: judges belong to events. Keyed on (event, judge), so re-runs
    add nothing."""
    from .judging.models import EventJudge

    for row in load_fixture("events.json"):
        event_id = slug_to_id[row["slug"]]
        for email in row.get("judge_emails", []):
            user_id = email_to_id[email]
            if not session.exec(
                select(EventJudge).where(EventJudge.event_id == event_id, EventJudge.user_id == user_id)
            ).first():
                session.add(EventJudge(event_id=event_id, user_id=user_id))


DOGFOOD_EVENT_SLUG = "sample-hack-2026"
# Every account the official fixtures create shares this password (README).
DOGFOOD_PASSWORD = "dogfood2026"
# Who the acceptance checker acts as (.dogfood.toml [auth]); the cookies that
# prove it come from DEMO_SESSION_TOKENS in docker-compose.yml.
CHECKER_ACCOUNTS = {
    "organizer": "alice@example.com",
    "judge_a": "tomas.varga@example.org",
    "judge_b": "wei.lindqvist@example.org",
    "participant": "priya1@example.org",
}


def _seed_dogfood(session: Session, path: Path) -> None:
    """Load the official DOGFOOD fixtures.json into our schema.

    Its shape is not ours (string ids, projects not submissions, scores with no
    assignments), so it gets its own step. The event slug guards the whole file,
    and run_seed commits once, so it lands all or nothing. The event closes at
    the fixture's submissions_close, which is in the past: the deadline check in
    submissions/router.py refuses every new submission, with no special case.
    """
    from .auth.models import Role, User
    from .auth.security import hash_password
    from .events.models import Event
    from .judging.models import EventJudge, JudgeAssignment, Rubric
    from .scoring.models import Score
    from .scoring.router import _weighted_total
    from .submissions.models import Submission, SubmissionStatus
    from .teams.models import Team, TeamMembership

    if not path.exists() or session.exec(select(Event).where(Event.slug == DOGFOOD_EVENT_SLUG)).first():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    organizer = session.exec(select(User).where(User.role == Role.organizer).order_by(User.id)).first()
    if organizer is None:
        log.warning("no organizer account to own the DOGFOOD event, skipping %s", path)
        return

    close = _fixture_dt(data["event"]["submissions_close"])
    tracks = {t["id"]: t["name"] for t in data["tracks"]}
    event = Event(
        slug=DOGFOOD_EVENT_SLUG,
        name=data["event"]["name"],
        description="Loaded from the DOGFOOD 2026 shared fixtures.",
        start_at=close - timedelta(hours=72),
        end_at=close,
        tracks=list(tracks.values()),
        created_by_id=organizer.id,
    )
    session.add(event)
    session.flush()

    # One hash for every fixture account: ~80 separate password hashes would
    # add seconds to every fresh boot for no security benefit on demo data.
    password_hash = hash_password(DOGFOOD_PASSWORD)

    def user_id(email: str, name: str, role: Role) -> int:
        user = session.exec(select(User).where(User.email == email)).first()
        if user is None:
            user = User(email=email, name=name, role=role, password_hash=password_hash, email_verified_at=utcnow())
            session.add(user)
            session.flush()
        return user.id

    judges = {j["id"]: user_id(j["email"], j["name"], Role.judge) for j in data["judges"]}
    for judge_id in judges.values():
        session.add(EventJudge(event_id=event.id, user_id=judge_id))

    teams: dict[str, int] = {}
    for row in data["teams"]:
        members = [user_id(email, email.split("@")[0], Role.participant) for email in row["members"]]
        team = Team(name=row["name"], event_id=event.id, captain_id=members[0] if members else None)
        session.add(team)
        session.flush()
        for member_id in members:
            session.add(TeamMembership(team_id=team.id, user_id=member_id))
        teams[row["id"]] = team.id

    # A team has one submission here, so the fixture's duplicate (a team that
    # submitted the same repo twice) folds into its first copy.
    submissions: dict[str, int] = {}
    by_team: dict[int, int] = {}
    for row in data["projects"]:
        team_id = teams[row["team"]]
        if team_id in by_team:
            log.info("fixture project %s duplicates an earlier one from team %s; merged", row["id"], row["team"])
            submissions[row["id"]] = by_team[team_id]
            continue
        at = _fixture_dt(row["submitted_at"])
        submission = Submission(
            team_id=team_id,
            event_id=event.id,
            title=row["title"],
            description=row.get("summary", ""),
            track=tracks.get(row.get("track"), ""),
            repo_url=row.get("repo_url", ""),
            status=SubmissionStatus.submitted,
            created_at=at,
            updated_at=at,
        )
        session.add(submission)
        session.flush()
        submissions[row["id"]] = by_team[team_id] = submission.id

    # The fixture names its criteria only inside the scores; weight them
    # equally on its own 1-5 scale, with the rounding remainder on the last so
    # the weights sum to exactly 1.0 as the assignment run requires.
    keys = list(dict.fromkeys(k for s in data["scores"] for k in s["criteria"]))
    weights = [round(1 / len(keys), 4)] * len(keys)
    weights[-1] = round(1 - sum(weights[:-1]), 4)
    criteria = [
        {"key": k, "label": k.capitalize(), "weight": w, "max_score": 5} for k, w in zip(keys, weights)
    ]
    session.add(Rubric(event_id=event.id, name="DOGFOOD Rubric", criteria=criteria))

    # The fixture has scores but no assignments, so each score implies one.
    # A judge who scored both copies of the duplicate counts once (first wins).
    seen: set[tuple[int, int]] = set()
    for row in data["scores"]:
        pair = (submissions[row["project"]], judges[row["judge"]])
        if pair in seen:
            continue
        seen.add(pair)
        assignment = JudgeAssignment(event_id=event.id, submission_id=pair[0], judge_id=pair[1])
        session.add(assignment)
        session.flush()
        session.add(
            Score(
                assignment_id=assignment.id,
                submission_id=pair[0],
                judge_id=pair[1],
                values=row["criteria"],
                comment=row.get("comment", ""),
                raw_total=_weighted_total(criteria, row["criteria"]),
            )
        )


def _print_checker_config(session: Session) -> None:
    """Print the .dogfood.toml [auth] and [routes] values at boot, as the spec
    asks. Ids are looked up rather than assumed, so a change in seeding order
    shows up here instead of as a mystery FAIL in the acceptance report."""
    from .auth.deps import DEMO_SESSION_TOKENS
    from .auth.models import User
    from .events.models import Event
    from .teams.models import Team, TeamMembership

    event = session.exec(select(Event).where(Event.slug == DOGFOOD_EVENT_SLUG)).first()
    if event is None or not DEMO_SESSION_TOKENS:
        return
    token_for = {email: token for token, email in DEMO_SESSION_TOKENS.items()}
    ids = {
        role: session.exec(select(User.id).where(User.email == email)).first()
        for role, email in CHECKER_ACCOUNTS.items()
    }
    team_id = session.exec(
        select(Team.id)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .where(Team.event_id == event.id, TeamMembership.user_id == ids["participant"])
    ).first()
    lines = ["seeded. acceptance checker config (.dogfood.toml):", "[auth]"]
    lines += [f'{role:<11} = "Cookie: session={token_for.get(email, "?")}"' for role, email in CHECKER_ACCOUNTS.items()]
    lines += [
        "[routes]",
        'gallery      = "/api/gallery"',
        f'submit       = "/api/teams/{team_id}/submission/submit"',
        'judge_scores = "/api/judges/me/scores"',
        f'peer_scores  = "/api/judges/{ids["judge_a"]}/scores"',
        f'csv_export   = "/api/events/{event.id}/export/scores.csv"',
    ]
    print("\n".join(lines), flush=True)


def run_seed() -> None:
    with Session(engine) as session:
        email_to_id = _seed_users(session)
        slug_to_id = _seed_events(session, email_to_id)
        name_to_id = _seed_teams(session, email_to_id, slug_to_id)
        _seed_submissions(session, slug_to_id, name_to_id)
        _seed_rubrics(session, slug_to_id)
        _seed_event_judges(session, email_to_id, slug_to_id)
        _seed_dogfood(session, FIXTURES_DIR / "dogfood.json")
        session.commit()
        _print_checker_config(session)
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
