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
    prize_config: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # Phase 3. voting_enabled gates the vote endpoints; results_hidden_until
    # gates who may see vote counts and standings, enforced in the response
    # itself rather than by hiding a control in the UI.
    voting_enabled: bool = Field(default=False)
    results_hidden_until: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_by_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
