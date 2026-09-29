"""Test fixtures: a dedicated Postgres database, one nested transaction per
test (rolled back after), and a TestClient wired to that transaction.

The target database is derived from the app's own DATABASE_URL with `_test`
appended, so `docker compose exec api pytest tests/ -v` works as documented in
PLAN.md without extra environment setup -- inside the container the host is
`db`, not `localhost`. Set TEST_DATABASE_URL to override entirely.
"""
import os

os.environ.setdefault("SESSION_SECRET", "test-secret-not-for-prod")

# Seeding is a startup side effect that commits on its OWN connection, outside
# each test's rolled-back transaction -- so seeded rows would persist for the
# whole session and leak into any query over a global table (e.g. "every user
# with role=judge"). Pointing FIXTURES_DIR at a path with no fixtures makes
# run_seed() a no-op under test; tests build exactly the data they assert on.
os.environ["FIXTURES_DIR"] = "/nonexistent-fixtures-under-test"

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

from app.db import (  # noqa: E402
    add_guarded_indexes,
    add_missing_columns,
    add_vote_voter_index,
    engine,
    protect_audit_log,
    widen_stored_file_key,
)
from app.auth import models as _auth_models  # noqa: E402,F401
from app.events import models as _event_models  # noqa: E402,F401
from app.teams import models as _team_models  # noqa: E402,F401
from app.submissions import models as _submission_models  # noqa: E402,F401
from app.judging import models as _judging_models  # noqa: E402,F401
from app.scoring import models as _scoring_models  # noqa: E402,F401
from app.voting import models as _voting_models  # noqa: E402,F401
from app.audit import models as _audit_models  # noqa: E402,F401
from app.auth import api_keys as _api_key_models  # noqa: E402,F401

SQLModel.metadata.create_all(engine)
# The test database outlives runs, so it needs the same column upgrades as a
# long-lived volume does (app.db.add_missing_columns).
add_missing_columns()
add_guarded_indexes()
widen_stored_file_key()
add_vote_voter_index()
protect_audit_log()


def _truncate_all() -> None:
    """Start every run from an empty schema.

    Each test rolls its own transaction back, but anything committed outside
    that transaction by an earlier run (or an earlier version of this file)
    would survive and quietly change what a query over a global table returns.
    A stale row here once made a coverage-shortfall test pass for the wrong
    reason, so the suite now refuses to inherit any state.
    """
    tables = ", ".join(f'"{t.name}"' for t in reversed(SQLModel.metadata.sorted_tables))
    if not tables:
        return
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


_truncate_all()


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


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """The limiter is process-global by design, so one test's spending would
    otherwise starve the next."""
    from app.ratelimit import reset_all

    reset_all()
    yield
    reset_all()


@pytest.fixture()
def client(session):
    from app.db import get_session
    from app.main import app

    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def webhook_deliveries(monkeypatch):
    """Audited actions queue webhook deliveries that go out after commit on a
    thread pool (webhooks/service.py). Under test they are captured here
    instead, so no test ever POSTs to a real URL, and a test can assert on what
    would have been sent: a list of (url, subscription_id, signed_payload)."""
    from app.webhooks import service

    sent: list = []
    monkeypatch.setattr(service, "_submit", lambda url, sub_id, signed: sent.append((url, sub_id, signed)))
    return sent


@pytest.fixture(autouse=True)
def _offline_dns(monkeypatch):
    """The webhook SSRF guard resolves hosts; tests must not need DNS. IP
    literals resolve to themselves, "localhost" to loopback, and any other
    name to a public documentation-range stand-in."""
    import ipaddress

    from app.webhooks import targets

    def resolve(host, port):
        try:
            return [str(ipaddress.ip_address(host.strip("[]")))]
        except ValueError:
            return ["127.0.0.1"] if host == "localhost" else ["93.184.215.14"]

    monkeypatch.setattr(targets, "_resolve", resolve)
