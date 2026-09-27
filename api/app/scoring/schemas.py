from typing import Dict, List

from pydantic import BaseModel, field_validator


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
