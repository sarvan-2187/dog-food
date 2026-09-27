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
    """PLAN.md Phase 2: weights must sum to 1.0 on save, rejected otherwise."""

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
    def weights_sum_to_one(self) -> "RubricWrite":
        keys = [c.key for c in self.criteria]
        if len(set(keys)) != len(keys):
            raise ValueError("Each criterion needs its own key.")
        total = sum(c.weight for c in self.criteria)
        if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            # The message names the actual total, so the organizer can see how
            # far off they are instead of guessing (PLAN.md 4.3).
            raise ValueError(f"Criteria weights must add up to 1.0 - they currently add up to {total:.4f}.")
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


class ScoringSheet(BaseModel):
    """Everything the score form needs in one call, scoped to the owning judge:
    the submission being judged, the rubric to judge it against, and this judge's
    own existing score if they have already given one."""

    assignment_id: int
    submission_id: int
    submission_title: str
    submission_description: str
    submission_track: str
    rubric_name: str
    criteria: List[dict]
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
    rubric_id: Optional[int] = None
