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


class GalleryImage(BaseModel):
    id: int
    url: str


class GalleryAnswer(BaseModel):
    question_id: str
    prompt: str
    answer: str


class GalleryItem(BaseModel):
    id: int
    event_id: int
    team_id: int
    title: str
    tagline: str = ""
    description: str
    track: str
    tech_tags: list[str] = []
    updated_at: datetime
    comment_count: int
    votes: Optional[int] = None
    voted_by_me: bool = False
    image_url: Optional[str] = None
    # The whole image gallery, in order; image_url is its first (the thumbnail).
    # Filled on the project page, left empty on gallery cards.
    images: list[GalleryImage] = []
    # Answers to questions the organizer chose to show publicly. Project page only.
    answers: list[GalleryAnswer] = []
    repo_url: str = ""
    demo_url: str = ""
    video_url: str = ""
    # Prize labels this project won (PLAN.md 10.6) - empty until results are
    # visible to the viewer, withheld in the response like vote counts.
    awards: list[str] = []


class PublicResultRow(BaseModel):
    rank: int
    submission_id: int
    submission_title: str
    team_name: str
    votes: int
