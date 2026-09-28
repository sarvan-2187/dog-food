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
    # Phase 3. voting_enabled gates the vote endpoints; results_hidden_until
    # gates who may see vote counts and standings, enforced in the response
    # itself rather than by hiding a control in the UI.
    voting_enabled: bool = Field(default=False)
    results_hidden_until: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # PLAN.md Phase 7.3: the "event.results_revealed" webhook topic fires once, the
    # first time any read happens after results_hidden_until has passed -- checked
    # lazily on read, not via a background scheduler this app has no other need for.
    results_revealed_notified: bool = Field(default=False)
    created_by_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
