from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

from ..timeutil import utcnow


def _ts_column() -> Column:
    """TIMESTAMP WITH TIME ZONE, so the offset survives the round trip."""
    return Column(DateTime(timezone=True), nullable=False)


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    name: str
    description: str = ""
    start_at: datetime = Field(sa_column=_ts_column())
    end_at: datetime = Field(sa_column=_ts_column())
    tracks: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Convention (PLAN.md Phase 7.1): {"prizes": [{"rank": "1st Place", "reward": "$500"}, ...]}.
    # A product decision, not a schema one -- kept as a loose JSON blob rather than a
    # dedicated table, since it's small, has no relational structure worth normalising, and
    # only this app's own UI ever reads or writes it.
    prize_config: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # PLAN.md Phase 7.2: matches this hackathon's own "Team Size: 1-4" rule as the default,
    # so existing seeded events keep behaving exactly as they do today with no fixture change.
    max_team_size: int = Field(default=4)
    # Cover art for the event card. A URL, not an upload: organizers overwhelmingly
    # already have a flyer hosted somewhere, and the /media store exists for
    # user-generated submission images, not for event chrome. None is a normal
    # state -- the web app falls back to a bundled photo (src/web/src/lib/event-cover.ts)
    # rather than rendering a hole in the grid.
    cover_image_url: Optional[str] = Field(default=None)
    # Phase 3. voting_enabled gates the vote endpoints; results_hidden_until
    # gates who may see vote counts and standings, enforced in the response
    # itself rather than by hiding a control in the UI.
    voting_enabled: bool = Field(default=False)
    # Who may vote while voting_enabled: "authenticated" (an account), "email"
    # (a guest who confirmed an emailed link) or "open" (anyone with the link).
    # See voting/voter.py and THREAT-MODEL.md for what each one does and does not stop.
    voting_access: str = Field(default="authenticated")
    # Opt-in sybil defences for account voters (THREAT-MODEL entry 25). Both off
    # by default so an offline install behaves exactly as before.
    voting_requires_verified: bool = Field(default=False)
    voting_account_cutoff: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    results_hidden_until: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # PLAN.md Phase 7.3: the "event.results_revealed" webhook topic fires once, the
    # first time any read happens after results_hidden_until has passed -- checked
    # lazily on read, not via a background scheduler this app has no other need for.
    results_revealed_notified: bool = Field(default=False)
    # When judges should be done. Soft: shown to judges and organizers, and a late
    # score is flagged in the audit log, but scoring never locks - a missed
    # deadline must not strand a project with no reviews.
    judging_deadline: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_by_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
    # "draft" | "published" (PLAN.md Phase 10.12). Defaults to published so seeded and
    # pre-10.12 events stay visible; POST /api/events and import set "draft" explicitly.
    status: str = Field(default="published")
    # Plain text shown on the event page, never rendered as HTML (PLAN.md 10.8).
    rules: str = ""
    # Named rounds shown as a timeline on the event page (Stage 1: Registration,
    # Stage 2: Build sprint, ...), like Unstop's rounds. Informational: the
    # server's own gates are still start_at / end_at / results_hidden_until.
    # [{"name", "description", "starts_at", "ends_at"}], ISO-8601 UTC, in order.
    stages: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON, nullable=False, server_default="[]"))
    # Which look its certificates use: a key of scoring.certificate.TEMPLATES.
    certificate_template: str = Field(default="classic")
    # Organizer-defined questions every team answers on the submission form
    # (DOGFOOD T1), at most 10: [{"id", "prompt", "required", "hidden", "public"}].
    # Short text answers live on Submission.answers under the question's id. A
    # question with answers can't be deleted, only hidden (events/questions.py).
    questions: List[Dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False, server_default="[]")
    )


class Announcement(SQLModel, table=True):
    """An organizer's message to an event's participants (PLAN.md Phase 10.11).
    Plain text only - never rendered as HTML."""

    __tablename__ = "announcements"

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="events.id", index=True)
    author_id: int = Field(foreign_key="users.id")
    title: str
    body: str
    emailed_count: int = 0
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
