"""Database engine and session dependency.

Single source of the engine for the whole app. Routers take `Session` via
`Depends(get_session)` and never build their own engine.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://dogfood:dogfood@localhost:5432/dogfood",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def create_db_and_tables() -> None:
    """Create any tables declared by imported SQLModel models.

    Phase 0 declares no models, so this is a no-op against an empty schema.
    From Phase 1 on, importing the model modules before calling this is what
    registers them on SQLModel.metadata.
    """
    SQLModel.metadata.create_all(engine)
    add_missing_columns()
    add_guarded_indexes()
    run_backfills()
    add_vote_voter_index()


# create_all() creates missing *tables* but never adds a column to one that
# already exists, so a volume from before a column was added crash-loops the
# API on boot (found live 2026-09-19 with events.cover_image_url). Each new
# column on an existing table gets one line here instead of a migration
# framework (PLAN.md Phase 9.1).
_ADDED_COLUMNS = (
    ("events", "cover_image_url", "varchar"),
    ("users", "session_version", "integer NOT NULL DEFAULT 0"),
    # PLAN.md Phase 10
    ("judge_invites", "event_id", "integer REFERENCES events(id)"),
    ("judge_invites", "grants_role", "varchar NOT NULL DEFAULT 'judge'"),
    ("team_memberships", "event_id", "integer REFERENCES events(id)"),
    ("teams", "captain_id", "integer REFERENCES users(id)"),
    ("submissions", "repo_url", "varchar NOT NULL DEFAULT ''"),
    ("submissions", "demo_url", "varchar NOT NULL DEFAULT ''"),
    ("submissions", "video_url", "varchar NOT NULL DEFAULT ''"),
    ("events", "status", "varchar NOT NULL DEFAULT 'published'"),
    ("events", "rules", "varchar NOT NULL DEFAULT ''"),
    ("users", "is_active", "boolean NOT NULL DEFAULT true"),
    # Voting access modes (DOGFOOD T3)
    ("events", "voting_access", "varchar NOT NULL DEFAULT 'authenticated'"),
    ("votes", "voter_key", "varchar"),
    # Known limits closed (docs/superpowers/specs/2026-09-27-known-limits-design.md)
    ("submissions", "disqualified_at", "timestamptz"),
    ("submissions", "disqualified_reason", "varchar NOT NULL DEFAULT ''"),
    ("events", "judging_deadline", "timestamptz"),
    ("events", "voting_requires_verified", "boolean NOT NULL DEFAULT false"),
    ("events", "voting_account_cutoff", "timestamptz"),
    ("users", "email_verified_at", "timestamptz"),
)


def add_missing_columns() -> None:
    """ALTER only when the column is really absent. `ADD COLUMN IF NOT EXISTS`
    alone still takes an exclusive table lock every boot, and waits forever
    behind any open transaction touching that table (found live: it hung the
    test suite)."""
    with engine.begin() as conn:
        for table, column, ddl in _ADDED_COLUMNS:
            present = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": column},
            ).first()
            if present is None:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}"))


log = logging.getLogger(__name__)

# Idempotent data fixes for rows written before a Phase 10 column existed. Each
# is safe to run on every boot: it only touches rows still missing the value.
_BACKFILLS = (
    # 10.2: which event each membership belongs to.
    "UPDATE team_memberships m SET event_id = t.event_id FROM teams t "
    "WHERE m.team_id = t.id AND m.event_id IS NULL",
    # 10.9: a team's captain is its earliest member.
    "UPDATE teams t SET captain_id = ("
    "  SELECT m.user_id FROM team_memberships m WHERE m.team_id = t.id ORDER BY m.joined_at, m.id LIMIT 1"
    ") WHERE t.captain_id IS NULL",
    # 10.1: every judge already assigned in an event belongs to that event's pool.
    "INSERT INTO event_judges (event_id, user_id, added_at) "
    "SELECT DISTINCT a.event_id, a.judge_id, now() FROM judge_assignments a "
    "ON CONFLICT (event_id, user_id) DO NOTHING",
)


def run_backfills() -> None:
    with engine.begin() as conn:
        for statement in _BACKFILLS:
            conn.execute(text(statement))


def duplicate_team_memberships() -> list[tuple[int, int, int]]:
    """(event_id, user_id, team count) for anyone on more than one team in one
    event - data written before PLAN.md 10.2 made that impossible. The admin
    dashboard lists these until an organizer resolves them."""
    with engine.connect() as conn:
        return [
            tuple(row)
            for row in conn.execute(
                text(
                    "SELECT event_id, user_id, count(*) FROM team_memberships WHERE event_id IS NOT NULL "
                    "GROUP BY event_id, user_id HAVING count(*) > 1 ORDER BY event_id, user_id"
                )
            )
        ]


def add_guarded_indexes() -> None:
    """10.2's database-level "one team per person per event". Created only when
    the existing data already satisfies it: an old volume with duplicates must
    still boot, so it logs them and tries again next boot instead of crashing.
    Checked in pg_indexes first for the same reason columns are (no lock taken
    when there's nothing to do)."""
    name = "uq_membership_event_user"
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_indexes WHERE indexname = :n"), {"n": name}).first()
        if exists:
            return
        # Memberships need their event_id before uniqueness can be judged.
        conn.execute(text(_BACKFILLS[0]))
    duplicates = duplicate_team_memberships()
    if duplicates:
        for event_id, user_id, count in duplicates:
            log.warning(
                "user %s is on %s teams in event %s - one-team-per-event index not created until resolved",
                user_id, count, event_id,
            )
        return
    with engine.begin() as conn:
        conn.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON team_memberships (event_id, user_id)"))


def add_vote_voter_index() -> None:
    """Guest votes: votes.user_id becomes nullable, every old vote gets the
    voter_key its account would get today (voting/voter.py email_key), then one
    unique index per (voter, submission). Each step checks first, so a booted
    volume takes no lock."""
    with engine.begin() as conn:
        nullable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'votes' AND column_name = 'user_id'"
            )
        ).scalar()
        if nullable == "NO":
            conn.execute(text("ALTER TABLE votes ALTER COLUMN user_id DROP NOT NULL"))
        if conn.execute(text("SELECT 1 FROM pg_indexes WHERE indexname = 'uq_vote_voter'")).first():
            return
        conn.execute(
            text(
                "UPDATE votes v SET voter_key = 'email:' || "
                "left(encode(sha256(convert_to(lower(u.email), 'UTF8')), 'hex'), 32) "
                "FROM users u WHERE v.user_id = u.id AND v.voter_key IS NULL"
            )
        )
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_vote_voter ON votes (voter_key, submission_id)"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
