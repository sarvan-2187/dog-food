from datetime import datetime
from typing import Optional

from urllib.parse import urlparse

from pydantic import BaseModel, field_validator


def safe_link(v: Optional[str]) -> Optional[str]:
    """http(s) only (PLAN.md 10.5): a `javascript:` or `data:` URL rendered as a
    link is a script waiting for a click. An empty string clears the link."""
    if v is None:
        return v
    v = v.strip()
    if not v:
        return ""
    if len(v) > 500:
        raise ValueError("Links must be 500 characters or fewer.")
    parsed = urlparse(v)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Enter a full web address starting with https:// (or http://).")
    return v


class SubmissionUpdate(BaseModel):
    """Autosave PATCH body. Every field is optional so the form can save one
    field at a time; an explicitly-null field is a no-op, not a 500."""

    title: Optional[str] = None
    description: Optional[str] = None
    track: Optional[str] = None
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None
    video_url: Optional[str] = None

    @field_validator("repo_url", "demo_url", "video_url")
    @classmethod
    def link(cls, v: Optional[str]) -> Optional[str]:
        return safe_link(v)

    @field_validator("title")
    @classmethod
    def title_len(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v.strip()) > 120:
            raise ValueError("Title must be 120 characters or fewer.")
        return v

    @field_validator("description")
    @classmethod
    def description_len(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v.strip()) > 5000:
            raise ValueError("Description must be 5000 characters or fewer.")
        return v


class SubmissionPublic(BaseModel):
    """Submission plus its uploaded image, if any (PLAN.md Phase 6) -- a
    plain Submission row has no such column; this is assembled by the
    router so the editing page can see an existing screenshot on load."""

    id: int
    team_id: int
    event_id: int
    title: str
    description: str
    track: str
    status: str
    created_at: datetime
    updated_at: datetime
    image_url: Optional[str] = None
    repo_url: str = ""
    demo_url: str = ""
    video_url: str = ""
