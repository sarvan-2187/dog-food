"""UTC time helpers.

Every datetime in this app is timezone-aware UTC, end to end:

* columns are ``TIMESTAMP WITH TIME ZONE`` (see the model modules), so Postgres
  keeps the offset instead of silently dropping it;
* ``utcnow()`` replaces ``datetime.utcnow()``, which is deprecated in 3.12 and
  returns a *naive* value that compares wrongly against an aware one;
* ``ensure_utc()`` normalises anything arriving from a client or a fixture, so a
  naive input is read as UTC rather than as the server's local time.

This matters at the edge, not just internally: a naive datetime serialises to
JSON with no offset (``2026-09-21T18:00:00``), and ``new Date()`` in the browser
reads that as *local* time. The deadline the participant sees then drifts by
their UTC offset from the one the API enforces.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current time as an aware UTC datetime."""
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    """Read a naive datetime as UTC; convert an aware one to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
