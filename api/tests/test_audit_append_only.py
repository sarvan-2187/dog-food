"""The audit log is append-only in the database, not only by convention
(PLAN.md section 9; spec compliance check, task 6)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.audit.models import AuditLog


def _row(session) -> AuditLog:
    entry = AuditLog(action="test.append_only", entity_type="test", detail={"n": 1})
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def test_rows_can_be_inserted_and_read(session):
    entry = _row(session)
    assert session.get(AuditLog, entry.id).action == "test.append_only"


def test_update_is_refused_by_the_database(session):
    entry = _row(session)
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(text("UPDATE audit_log SET action = 'forged' WHERE id = :i"), {"i": entry.id})
    session.rollback()


def test_delete_is_refused_by_the_database(session):
    entry = _row(session)
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(text("DELETE FROM audit_log WHERE id = :i"), {"i": entry.id})
    session.rollback()


def test_orm_update_is_refused_too(session):
    entry = _row(session)
    entry.action = "forged"
    session.add(entry)
    with pytest.raises(DBAPIError):
        session.commit()
    session.rollback()


def test_guard_is_idempotent():
    from app.db import protect_audit_log

    protect_audit_log()
    protect_audit_log()
