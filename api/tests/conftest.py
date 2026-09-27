"""Test fixtures: a dedicated Postgres database, one nested transaction per
test (rolled back after), and a TestClient wired to that transaction.

The target database is derived from the app's own DATABASE_URL with `_test`
appended, so `docker compose exec api pytest tests/ -v` works as documented in
PLAN.md without extra environment setup -- inside the container the host is
`db`, not `localhost`. Set TEST_DATABASE_URL to override entirely.
"""
import os

os.environ.setdefault("SESSION_SECRET", "test-secret-not-for-prod")

_DEV_FALLBACK = "postgresql+psycopg2://dogfood:dogfood@localhost:5432/dogfood"


def _test_database_url() -> str:
    """Point at <app database>_test, on whichever host the app itself uses."""
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base, _, name = os.getenv("DATABASE_URL", _DEV_FALLBACK).rpartition("/")
    name = name.split("?", 1)[0]
    return f"{base}/{name}_test" if name else f"{_DEV_FALLBACK}_test"


os.environ["DATABASE_URL"] = _test_database_url()

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlmodel import SQLModel, Session


def _ensure_test_database(url: str) -> None:
    db_name = url.rsplit("/", 1)[1]
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}).first()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()


_ensure_test_database(os.environ["DATABASE_URL"])

from app.db import engine  # noqa: E402
from app.auth import models as _auth_models  # noqa: E402,F401
from app.events import models as _event_models  # noqa: E402,F401
from app.teams import models as _team_models  # noqa: E402,F401
from app.submissions import models as _submission_models  # noqa: E402,F401

SQLModel.metadata.create_all(engine)


@pytest.fixture()
def session():
    connection = engine.connect()
    outer_transaction = connection.begin()
    # create_savepoint keeps route-handler session.commit() calls from ending
    # the outer transaction, so the whole test still rolls back cleanly.
    db_session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield db_session
    finally:
        db_session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture()
def client(session):
    from app.db import get_session
    from app.main import app

    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
