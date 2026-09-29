import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

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
    max_team_size: int = 4
    cover_image_url: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_len(cls, v: str) -> str:
        return _name_len(v)

    @field_validator("max_team_size")
    @classmethod
    def team_size_range(cls, v: int) -> int:
        if not (1 <= v <= 20):
            raise ValueError("Max team size must be between 1 and 20.")
        return v

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


class Stage(BaseModel):
    """One round of an event (Stage 1, Stage 2, ...). Shown, not enforced."""

    name: str
    description: str = ""
    starts_at: datetime
    ends_at: datetime

    @field_validator("name")
    @classmethod
    def name_len(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 60):
            raise ValueError("A stage name must be 1-60 characters.")
        return v

    @field_validator("description")
    @classmethod
    def description_len(cls, v: str) -> str:
        if len(v) > 300:
            raise ValueError("A stage description must be 300 characters or fewer.")
        return v.strip()

    @field_validator("starts_at", "ends_at")
    @classmethod
    def as_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)

    @model_validator(mode="after")
    def ordered(self) -> "Stage":
        if self.ends_at <= self.starts_at:
            raise ValueError(f"Stage \"{self.name}\" must end after it starts.")
        return self


MAX_STAGES = 10


def stages_to_json(stages: List[Stage]) -> List[Dict[str, Any]]:
    """Chronological, JSON-ready. Overlaps are allowed (a judging round can
    start while a showcase runs); the order is by start time."""
    if len(stages) > MAX_STAGES:
        raise ValueError(f"An event can have at most {MAX_STAGES} stages.")
    return [s.model_dump(mode="json") for s in sorted(stages, key=lambda s: s.starts_at)]


class EventUpdate(BaseModel):
    """PATCH must not be a way around EventCreate's rules, so it revalidates the
    same ones on whichever fields are present."""

    name: Optional[str] = None
    description: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    tracks: Optional[List[str]] = None
    prize_config: Optional[Dict[str, Any]] = None
    max_team_size: Optional[int] = None
    cover_image_url: Optional[str] = None
    voting_enabled: Optional[bool] = None
    voting_access: Optional[Literal["authenticated", "email", "open"]] = None
    results_hidden_until: Optional[datetime] = None
    judging_deadline: Optional[datetime] = None
    voting_requires_verified: Optional[bool] = None
    voting_account_cutoff: Optional[datetime] = None
    rules: Optional[str] = None
    stages: Optional[List[Stage]] = None

    @field_validator("name")
    @classmethod
    def name_len(cls, v: Optional[str]) -> Optional[str]:
        return v if v is None else _name_len(v)

    @field_validator("stages")
    @classmethod
    def stage_count(cls, v: Optional[List[Stage]]) -> Optional[List[Stage]]:
        if v is not None and len(v) > MAX_STAGES:
            raise ValueError(f"An event can have at most {MAX_STAGES} stages.")
        return v

    @field_validator("rules")
    @classmethod
    def rules_len(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 5000:
            raise ValueError("Rules must be 5000 characters or fewer.")
        return v

    @field_validator("max_team_size")
    @classmethod
    def team_size_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 20):
            raise ValueError("Max team size must be between 1 and 20.")
        return v

    @field_validator("start_at", "end_at", "results_hidden_until", "judging_deadline", "voting_account_cutoff")
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
