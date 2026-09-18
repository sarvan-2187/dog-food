from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class CommentWrite(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def body_len(cls, v: str) -> str:
        v = v.strip()
        if not (2 <= len(v) <= 1000):
            raise ValueError("A comment must be between 2 and 1000 characters.")
        return v


class CommentPublic(BaseModel):
    id: int
    submission_id: int
    author_name: str
    body: str
    created_at: datetime


class VoteResult(BaseModel):
    submission_id: int
    voted: bool
    # None while results are hidden -- the count is withheld in the response, not
    # merely hidden by the UI (PLAN.md Phase 3).
    votes: Optional[int] = None


class GalleryItem(BaseModel):
    id: int
    event_id: int
    team_id: int
    title: str
    description: str
    track: str
    updated_at: datetime
    comment_count: int
    votes: Optional[int] = None
    voted_by_me: bool = False
    image_url: Optional[str] = None


class PublicResultRow(BaseModel):
    rank: int
    submission_id: int
    submission_title: str
    team_name: str
    votes: int
