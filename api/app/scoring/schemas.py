from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, field_validator

from ..events.schemas import Stage
from ..submissions.schemas import safe_link


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
    description: str = ""
    track: str = ""
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
    rubrics: List[RubricImport] = []
    teams: List[TeamImport] = []
    submissions: List[SubmissionImport] = []
