from datetime import datetime
from typing import Dict, List, Optional

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


MAX_TAGLINE = 140
MAX_TAGS = 10
MAX_TAG_LEN = 30
MAX_ANSWER = 1000
MAX_IMAGES = 5


def clean_tags(tags: List[str]) -> List[str]:
    """Trimmed, inner whitespace collapsed, and deduplicated case-insensitively
    (the first spelling wins). Matching is always on the lowercased form."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = " ".join(str(raw).split())
        if not tag:
            continue
        if len(tag) > MAX_TAG_LEN:
            raise ValueError(f"Each tech tag must be {MAX_TAG_LEN} characters or fewer.")
        if tag.lower() not in seen:
            seen.add(tag.lower())
            out.append(tag)
    if len(out) > MAX_TAGS:
        raise ValueError(f"Add at most {MAX_TAGS} tech tags.")
    return out


class SubmissionUpdate(BaseModel):
    """Autosave PATCH body. Every field is optional so the form can save one
    field at a time; an explicitly-null field is a no-op, not a 500."""

    title: Optional[str] = None
    tagline: Optional[str] = None
    description: Optional[str] = None
    track: Optional[str] = None
    tech_tags: Optional[List[str]] = None
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None
    video_url: Optional[str] = None
    # Merged into the saved answers, so the form can autosave one question at a
    # time. Keys are question ids; the router checks they belong to the event.
    answers: Optional[Dict[str, str]] = None

    @field_validator("tagline")
    @classmethod
    def tagline_len(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = " ".join(v.split())
        if len(v) > MAX_TAGLINE:
            raise ValueError(f"Tagline must be {MAX_TAGLINE} characters or fewer.")
        return v

    @field_validator("tech_tags")
    @classmethod
    def tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return None if v is None else clean_tags(v)

    @field_validator("answers")
    @classmethod
    def answer_len(cls, v: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        if v is None:
            return v
        v = {k: a.strip() for k, a in v.items()}
        if any(len(a) > MAX_ANSWER for a in v.values()):
            raise ValueError(f"Each answer must be {MAX_ANSWER} characters or fewer.")
        return v

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


class SubmissionImage(BaseModel):
    """One picture in a submission's gallery. The first is the thumbnail."""

    id: int
    url: str


class AnswerPublic(BaseModel):
    question_id: str
    prompt: str
    answer: str


class ImageOrder(BaseModel):
    image_ids: List[int]


class SubmissionPublic(BaseModel):
    """Submission plus its uploaded image, if any (PLAN.md Phase 6) -- a
    plain Submission row has no such column; this is assembled by the
    router so the editing page can see an existing screenshot on load."""

    id: int
    team_id: int
    event_id: int
    title: str
    tagline: str = ""
    description: str
    track: str
    tech_tags: List[str] = []
    status: str
    created_at: datetime
    updated_at: datetime
    image_url: Optional[str] = None
    images: List[SubmissionImage] = []
    # The team's own answers, keyed by question id.
    answers: Dict[str, str] = {}
    repo_url: str = ""
    demo_url: str = ""
    video_url: str = ""
    disqualified_at: Optional[datetime] = None
    disqualified_reason: str = ""


class EligibilityRow(BaseModel):
    submission_id: int
    title: str
    team_name: str
    disqualified_at: Optional[datetime] = None
    disqualified_reason: str = ""
    # Automatic checks (no repo, duplicate repo, thin description, no track,
    # oversized team). Advisory: the organizer still makes every ruling.
    flags: list[str] = []


class EligibilityUpdate(BaseModel):
    """An organizer's decision. Disqualifying needs a reason the team will see."""

    eligible: bool
    reason: str = ""
