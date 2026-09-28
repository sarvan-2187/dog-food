from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Weights are floats, so an exact == 1.0 test would reject 0.3+0.3+0.4. The
# tolerance is tight enough that a genuine mistake (0.3/0.3/0.3) still fails.
WEIGHT_SUM_TOLERANCE = 1e-6


class CriterionWrite(BaseModel):
    key: str
    label: str
    weight: float
    max_score: float = 10.0
    # What the criterion means, shown to judges under the field and to
    # participants on the event page (PLAN.md 10.8). Criteria are stored as
    # JSON, so this needs no schema change.
    description: str = ""

    @field_validator("description")
    @classmethod
    def description_len(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 300:
            raise ValueError("A criterion description must be 300 characters or fewer.")
        return v

    @field_validator("key")
    @classmethod
    def key_format(cls, v: str) -> str:
        v = v.strip()
        if not v or not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Criterion key must be letters, numbers, dashes or underscores.")
        return v

    @field_validator("label")
    @classmethod
    def label_len(cls, v: str) -> str:
        v = v.strip()
        if not (2 <= len(v) <= 60):
            raise ValueError("Criterion label must be 2-60 characters.")
        return v

    @field_validator("weight")
    @classmethod
    def weight_range(cls, v: float) -> float:
        if not (0 < v <= 1):
            raise ValueError("Each weight must be greater than 0 and at most 1.")
        return v

    @field_validator("max_score")
    @classmethod
    def max_score_range(cls, v: float) -> float:
        if not (0 < v <= 100):
            raise ValueError("Maximum score must be between 1 and 100.")
        return v


class RubricWrite(BaseModel):
    """One rubric within an event's rubric set. Keys must be unique within
    this rubric (checked here) AND across every other rubric in the same
    event (a cross-row check the router does, since a single rubric's own
    payload can't see its siblings). The combined weight-sums-to-1.0 rule
    is enforced when judges are assigned, not here -- an organizer builds
    the set up one rubric at a time, and a lone rubric summing to e.g. 0.35
    is normal mid-setup, not a mistake."""

    name: str
    criteria: List[CriterionWrite] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def name_len(cls, v: str) -> str:
        v = v.strip()
        if not (3 <= len(v) <= 80):
            raise ValueError("Rubric name must be 3-80 characters.")
        return v

    @model_validator(mode="after")
    def keys_unique_within_rubric(self) -> "RubricWrite":
        keys = [c.key for c in self.criteria]
        if len(set(keys)) != len(keys):
            raise ValueError("Each criterion needs its own key.")
        return self


class AssignmentRun(BaseModel):
    judges_per_submission: int = 3

    @field_validator("judges_per_submission")
    @classmethod
    def k_range(cls, v: int) -> int:
        if not (1 <= v <= 10):
            raise ValueError("Judges per submission must be between 1 and 10.")
        return v


class AssignmentPublic(BaseModel):
    id: int
    submission_id: int
    judge_id: int
    submission_title: str
    scored: bool
    # Carried so a judge's own dashboard can group their work by event and
    # request the signed participation record for it (PLAN.md Phase 4 T4),
    # which is keyed on event_id -- the dashboard has no other route to it.
    event_id: int
    event_name: str
    # The event's soft judging deadline, if the organizer set one.
    due_at: Optional[datetime] = None


class RubricGroup(BaseModel):
    """One rubric's own slice of the combined score form, so the UI can
    group criteria under the rubric's name instead of showing one
    undifferentiated list."""

    rubric_id: int
    rubric_name: str
    criteria: List[dict]


class ScoringSheet(BaseModel):
    """Everything the score form needs in one call, scoped to the owning judge:
    the submission being judged, every rubric in the event grouped with its own
    criteria, and this judge's own existing score if they have already given
    one. `my_values` is still one flat dict keyed by criterion key across all
    rubrics, matching how Score.values is stored."""

    assignment_id: int
    submission_id: int
    submission_title: str
    submission_description: str
    submission_track: str
    submission_image_url: Optional[str] = None
    repo_url: str = ""
    demo_url: str = ""
    video_url: str = ""
    rubrics: List[RubricGroup]
    my_values: Optional[dict] = None
    my_comment: str = ""
    my_raw_total: Optional[float] = None


class JudgeProgress(BaseModel):
    """Leads with the numbers the dashboard puts above the fold (PLAN.md 4.4)."""

    completed: int
    total: int
    pending: List[AssignmentPublic]
    done: List[AssignmentPublic]


class CoverageWarning(BaseModel):
    submission_id: int
    submission_title: str
    judges_short: int


class AssignmentSummary(BaseModel):
    created: int
    existing: int
    judges_per_submission: int
    coverage_warnings: List[CoverageWarning]
