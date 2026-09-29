"""Outbound webhook subscriptions (PLAN.md Phase 7.3)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from ..timeutil import utcnow


def _ts_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False)


class WebhookSubscription(SQLModel, table=True):
    """An organizer-configured URL that receives a signed POST when
    something consequential happens in their event. Entirely opt-in --
    zero outbound calls exist until one of these rows does. `last_status`
    is the cheapest honest answer to "did my webhook actually fire" without
    a separate delivery-log table this feature's scale doesn't need."""

    __tablename__ = "webhook_subscriptions"

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="events.id", index=True)
    url: str
    created_by_id: int = Field(foreign_key="users.id")
    active: bool = Field(default=True)
    last_status: str = Field(default="never fired")  # "never fired" | "delivered" | "failed"
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts_column())
