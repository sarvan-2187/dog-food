from typing import Optional

from pydantic import BaseModel, field_validator


class SubmissionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    track: Optional[str] = None

    @field_validator("title")
    @classmethod
    def title_len(cls, v: str) -> str:
        if len(v.strip()) > 120:
            raise ValueError("Title must be 120 characters or fewer.")
        return v
