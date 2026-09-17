import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator

from ..timeutil import ensure_utc

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _name_len(v: str) -> str:
    v = v.strip()
    if not (3 <= len(v) <= 80):
        raise ValueError("Event name must be 3-80 characters.")
    return v


class EventCreate(BaseModel):
    name: str
    slug: str
    description: str = ""
    start_at: datetime
    end_at: datetime
    tracks: List[str] = []
    prize_config: Dict[str, Any] = {}

    @field_validator("name")
    @classmethod
    def name_len(cls, v: str) -> str:
        return _name_len(v)

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("Slug must be lowercase letters, numbers and dashes.")
        return v

    @field_validator("start_at", "end_at")
    @classmethod
    def as_utc(cls, v: datetime) -> datetime:
        """A client may post a naive datetime; read it as UTC, never as server-local."""
        return ensure_utc(v)

    @field_validator("end_at")
    @classmethod
    def end_after_start(cls, v: datetime, info) -> datetime:
        start = info.data.get("start_at")
        if start and v <= start:
            raise ValueError("End date must be after the start date.")
        return v


class EventUpdate(BaseModel):
    """PATCH must not be a way around EventCreate's rules, so it revalidates the
    same ones on whichever fields are present."""

    name: Optional[str] = None
    description: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    tracks: Optional[List[str]] = None
    prize_config: Optional[Dict[str, Any]] = None

    @field_validator("name")
    @classmethod
    def name_len(cls, v: Optional[str]) -> Optional[str]:
        return v if v is None else _name_len(v)

    @field_validator("start_at", "end_at")
    @classmethod
    def as_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        return v if v is None else ensure_utc(v)

    @model_validator(mode="after")
    def dates_ordered(self) -> "EventUpdate":
        # Only checkable when the request carries both ends; a one-sided change is
        # re-checked against the stored row in the router, which has the other end.
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValueError("End date must be after the start date.")
        return self
