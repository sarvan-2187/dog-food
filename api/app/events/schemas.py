import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


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
        v = v.strip()
        if not (3 <= len(v) <= 80):
            raise ValueError("Event name must be 3-80 characters.")
        return v

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("Slug must be lowercase letters, numbers and dashes.")
        return v

    @field_validator("end_at")
    @classmethod
    def end_after_start(cls, v: datetime, info) -> datetime:
        start = info.data.get("start_at")
        if start and v <= start:
            raise ValueError("End date must be after the start date.")
        return v


class EventUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    tracks: Optional[List[str]] = None
    prize_config: Optional[Dict[str, Any]] = None
