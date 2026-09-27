"""Database engine and session dependency.

Single source of the engine for the whole app. Routers take `Session` via
`Depends(get_session)` and never build their own engine.
"""
from __future__ import annotations

import os
from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://dogfood:dogfood@localhost:5432/dogfood",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def create_db_and_tables() -> None:
    """Create any tables declared by imported SQLModel models.

    Phase 0 declares no models, so this is a no-op against an empty schema.
    From Phase 1 on, importing the model modules before calling this is what
    registers them on SQLModel.metadata.
    """
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
