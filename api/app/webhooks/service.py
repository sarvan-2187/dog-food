"""Signed, best-effort webhook delivery (PLAN.md Phase 7.3).

Fire-and-forget: one attempt, dispatched via FastAPI BackgroundTasks so a
slow or unreachable endpoint never delays the request that triggered it.
No queue, no retry/backoff -- a retry system is real infrastructure this
hackathon-scale platform does not need (see PLAN.md Phase 7.3's own
reasoning), and building one would be exactly the kind of unfinished
feature that adds risk to `docker compose up` for no acceptance-suite
benefit. Payloads are signed with the same Ed25519 key and canonical-JSON
scheme already built for Phase 4's judge participation records
(api/app/crypto.py) -- a receiver who already verifies those needs zero
new code to verify a webhook too.
"""
from __future__ import annotations

import httpx
from fastapi import BackgroundTasks
from sqlmodel import Session, select

from .. import crypto
from ..timeutil import utcnow
from .models import WebhookSubscription

TIMEOUT_SECONDS = 5.0


def _deliver(url: str, subscription_id: int, signed_payload: dict, *, session: "Session | None" = None) -> None:
    """Runs in a background task, after the response that triggered it has
    already been sent -- never raises back into that request. Records its
    own outcome so an organizer has real feedback, not a fire-into-the-void
    control.

    `session` is a testability seam only: production callers (via `notify()`
    below) never pass one, since the real request-scoped session is already
    closed by the time a background task runs and a fresh one is opened
    against `engine`. Tests that need to see the status update within their
    own transaction pass their own session directly instead."""
    status_text = "failed"
    try:
        response = httpx.post(url, json=signed_payload, timeout=TIMEOUT_SECONDS)
        if response.is_success:
            status_text = "delivered"
    except httpx.HTTPError:
        status_text = "failed"

    def _record_status(s: Session) -> None:
        row = s.get(WebhookSubscription, subscription_id)
        if row:
            row.last_status = status_text
            s.add(row)
            s.commit()

    if session is not None:
        _record_status(session)
    else:
        from ..db import engine  # local import: keep this module free of a load-time DB dependency

        with Session(engine) as fresh_session:
            _record_status(fresh_session)


def notify(session: Session, background_tasks: BackgroundTasks, event_id: int, topic: str, **detail) -> None:
    """Called at the same handful of sites that already call audit.log.record()
    for these topics -- no new event-bus abstraction, since those call sites
    are already the single source of truth for "this consequential thing
    just happened". A no-op when the event has no active subscriptions, so
    calling this everywhere it applies costs nothing for the common case of
    zero webhooks configured."""
    subscriptions = session.exec(
        select(WebhookSubscription).where(
            WebhookSubscription.event_id == event_id,
            WebhookSubscription.active == True,  # noqa: E712 -- SQLAlchemy needs `== True`, not `is True`
        )
    ).all()
    if not subscriptions:
        return
    payload = {"topic": topic, "event_id": event_id, "issued_at": utcnow().isoformat(), **detail}
    signed = crypto.sign_record(payload)
    for sub in subscriptions:
        background_tasks.add_task(_deliver, sub.url, sub.id, signed)
