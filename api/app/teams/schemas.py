from datetime import datetime

from pydantic import BaseModel, field_validator


class TeamCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_len(cls, v: str) -> str:
        v = v.strip()
        if not (3 <= len(v) <= 40):
            raise ValueError("Team name must be 3-40 characters.")
        return v


class TeamJoin(BaseModel):
    invite_code: str


class TeamRename(TeamCreate):
    """Same 3-40 character rule as creation (PLAN.md 10.9)."""


class CaptainChange(BaseModel):
    user_id: int


class TeamMemberPublic(BaseModel):
    id: int
    name: str
    email: str


class TeamPublic(BaseModel):
    id: int
    event_id: int
    name: str
    invite_code: str
    members: list[TeamMemberPublic]
    max_team_size: int
    captain_id: int | None = None
    invite_code_expires_at: datetime | None = None

