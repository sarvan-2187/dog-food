from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, field_validator

from ..events.questions import MAX_QUESTIONS, QuestionWrite
from ..events.schemas import Stage
from ..submissions.schemas import MAX_ANSWER, MAX_TAGLINE, clean_tags, safe_link


class ScoreWrite(BaseModel):
    """`values` maps criterion key -> raw value. Completeness and range are
    checked against the event's rubric in the router, which is the only place
    that knows the criteria."""

    values: Dict[str, float]
    comment: str = ""

    @field_validator("comment")
    @classmethod
    def comment_len(cls, v: str) -> str:
        if len(v) > 2000:
            raise ValueError("Comment must be 2000 characters or fewer.")
        return v


class ScorePublic(BaseModel):
    id: int
    assignment_id: int
    submission_id: int
    values: Dict[str, float]
    comment: str
    raw_total: float


class ResultRow(BaseModel):
    rank: int
    submission_id: int
    submission_title: str
    team_name: str
    judges: int
    raw_mean: float
    z_bar: float
    display: float


# ---------------------------------------------------------------------------
# Bulk event import (PLAN.md Phase 4 T4). Deliberately scoped to the data an
# organizer would restore or migrate -- config, teams, and submissions.
# Judge assignments/scores are tied to specific judge accounts and are not
# re-created on import (see the router docstring for why).
# ---------------------------------------------------------------------------

class RubricImport(BaseModel):
    name: str
    criteria: List[Dict[str, Any]]


class SubmissionImport(BaseModel):
    team_name: str
    title: str = ""
    tagline: str = ""
    description: str = ""
    track: str = ""
    tech_tags: List[str] = []
    # Answers to the event's custom questions, keyed by question id.
    answers: Dict[str, str] = {}
    status: str = "draft"
    # PLAN.md 10.5 - a backup file is untrusted input, so links get the same
    # http(s)-only rule as the submission form.
    repo_url: str = ""
    demo_url: str = ""
    video_url: str = ""

    @field_validator("repo_url", "demo_url", "video_url")
    @classmethod
    def link(cls, v: str) -> str:
        return safe_link(v) or ""

    # The same limits as the submission form: a backup file is untrusted input.
    @field_validator("tagline")
    @classmethod
    def tagline_len(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) > MAX_TAGLINE:
            raise ValueError(f"Tagline must be {MAX_TAGLINE} characters or fewer.")
        return v

    @field_validator("tech_tags")
    @classmethod
    def tags(cls, v: List[str]) -> List[str]:
        return clean_tags(v)

    @field_validator("answers")
    @classmethod
    def answer_len(cls, v: Dict[str, str]) -> Dict[str, str]:
        if any(len(str(a)) > MAX_ANSWER for a in v.values()):
            raise ValueError(f"Each answer must be {MAX_ANSWER} characters or fewer.")
        return {k: str(a).strip() for k, a in v.items()}


class TeamImport(BaseModel):
    name: str


class EventImportPayload(BaseModel):
    slug: str
    name: str
    description: str = ""
    start_at: str
    end_at: str
    tracks: List[str] = []
    prize_config: Dict[str, Any] = {}
    voting_enabled: bool = False
    voting_access: Literal["authenticated", "email", "open"] = "authenticated"
    results_hidden_until: Optional[str] = None
    rules: str = ""
    stages: List[Stage] = []
    certificate_template: str = "classic"
    # Custom questions keep their ids, so the submissions' answers still match.
    questions: List[QuestionWrite] = []
    rubrics: List[RubricImport] = []
    teams: List[TeamImport] = []
    submissions: List[SubmissionImport] = []

    @field_validator("questions")
    @classmethod
    def question_count(cls, v: List[QuestionWrite]) -> List[QuestionWrite]:
        if len(v) > MAX_QUESTIONS:
            raise ValueError(f"An event can have at most {MAX_QUESTIONS} questions.")
        return v
