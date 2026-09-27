from typing import Optional

from pydantic import BaseModel, field_validator


class SubmissionUpdate(BaseModel):
    """Autosave PATCH body. Every field is optional so the form can save one
    field at a time; an explicitly-null field is a no-op, not a 500."""

    title: Optional[str] = None
    description: Optional[str] = None
    track: Optional[str] = None

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
