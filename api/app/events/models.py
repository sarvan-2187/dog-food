from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    name: str
    description: str = ""
    start_at: datetime
    end_at: datetime
    tracks: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    prize_config: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_by_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
