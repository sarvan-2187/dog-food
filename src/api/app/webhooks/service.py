"""Signed, best-effort webhook delivery (PLAN.md Phase 7.3).

Fire-and-forget: one attempt, dispatched via FastAPI BackgroundTasks so a
slow or unreachable endpoint never delays the request that triggered it.
No queue, no retry/backoff -- a retry system is real infrastructure this
hackathon-scale platform does not need (see PLAN.md Phase 7.3's own
reasoning), and building one would be exactly the kind of unfinished
feature that adds risk to `docker compose up` for no acceptance-suite
benefit. Payloads are signed with the same Ed25519 key and canonical-JSON
scheme already built for Phase 4's judge participation records
(src/api/app/crypto.py) -- a receiver who already verifies those needs zero
new code to verify a webhook too.
"""
from __future__ import annotations

import logging
import secrets
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import httpx
from fastapi import BackgroundTasks
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session as OrmSession
from sqlmodel import Session, select

from .. import crypto
from ..timeutil import utcnow
from .models import WebhookSubscription
from .targets import refusal

TIMEOUT_SECONDS = 5.0
USER_AGENT = "HackFlow-Webhooks/1.0"

# The SSRF guard lives in targets.py (refusal), checked at creation and delivery.

log = logging.getLogger("hackflow.webhooks")


def _delivery_id() -> str:
    """Unique per payload and inside the signed record, so a receiver can
    de-duplicate and refuse a replayed delivery."""
    return secrets.token_hex(12)


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
    # Checked again at delivery, not only at creation: DNS may have changed.
    # Refused is its own outcome, so an organizer can tell "we would not call
    # that address" apart from "we called it and it did not answer".
    if problem := refusal(url):
        log.info("webhook %s blocked: %s", subscription_id, problem)
        status_text = "blocked"
    else:
        record = signed_payload.get("record") or {}
        headers = {
            "User-Agent": USER_AGENT,
            "X-HackFlow-Topic": str(record.get("topic", "")),
            "X-HackFlow-Delivery": str(record.get("delivery_id", "")),
        }
        try:
            # Redirects are never followed: a public URL answering 302 to
            # http://169.254.169.254/ must not work.
            response = httpx.post(
                url, json=signed_payload, timeout=TIMEOUT_SECONDS, headers=headers, follow_redirects=False
            )
            if response.is_success:
                status_text = "delivered"
        except Exception:  # noqa: BLE001 - any failure is "failed", never an unhandled error in a worker
            # Not only httpx.HTTPError: a malformed URL raises httpx.InvalidURL,
            # which is not one, and used to escape here without recording anything.
            log.info("webhook %s delivery failed", subscription_id, exc_info=True)
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
    for sub in subscriptions:
        # One signed payload per subscription, each with its own delivery_id,
        # so a receiver can drop a replayed or duplicated delivery.
        payload = {
            "topic": topic,
            "event_id": event_id,
            "issued_at": utcnow().isoformat(),
            "delivery_id": _delivery_id(),
            **detail,
        }
        background_tasks.add_task(_deliver, sub.url, sub.id, crypto.sign_record(payload))


# --------------------------------------------------------------------------
# Every audited action (DOGFOOD T4: "webhooks covering every action the UI can
# take"). audit.log.record() is the one place every consequential action
# already passes through, so it hands each entry to queue_audited() below and
# no call site changes. The topic is the audit action string exactly.
# --------------------------------------------------------------------------

# Topics notify() already sends from its own call sites, with their own payload
# shape. record() leaves these alone, so each one still goes out exactly once.
NOTIFY_TOPICS = frozenset(
    {
        "assignments.run",
        "submission.submitted",
        "submission.disqualified",
        "submission.reinstated",
        "score.submitted",
        "announcement.posted",
        "event.results_revealed",
    }
)

# Audit detail keys that are ids but still say who voted. Never sent.
_PRIVATE_ID_KEYS = frozenset({"vote_id", "voter_user_id"})

_PENDING = "webhooks.pending"

# Deliveries leave the request thread, like notify()'s BackgroundTasks, so a
# slow receiver never holds up the response. A handful of workers is plenty at
# hackathon scale; each delivery is one POST with a 5 second timeout.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="webhook")


def _submit(url: str, subscription_id: int, signed_payload: dict) -> None:
    """Seam for tests, which run deliveries inline instead of on the pool."""
    _executor.submit(_deliver, url, subscription_id, signed_payload)


def _event_id_for(session: Session, entity_type: str, entity_id: Optional[int], detail: dict) -> Optional[int]:
    """Which event an audited action belongs to, or None for platform-wide ones
    (accounts, API keys, admin actions): webhooks are per event, so those send
    nothing."""
    # Local imports: these models' modules import audit.log, which imports us.
    from ..judging.models import JudgeInvite
    from ..submissions.models import Submission
    from ..teams.models import Team
    from ..voting.models import Comment

    if isinstance(detail.get("event_id"), int):
        return detail["event_id"]
    if entity_id is None:
        return None
    if entity_type == "event":
        return entity_id
    model = {"submission": Submission, "team": Team, "comment": Comment, "judge_invite": JudgeInvite}.get(entity_type)
    row = session.get(model, entity_id) if model else None
    return getattr(row, "event_id", None)


def queue_audited(
    session: Session, action: str, entity_type: str, entity_id: Optional[int], detail: dict[str, Any]
) -> None:
    """Stage a signed delivery of this audited action to each of its event's
    active webhooks. Nothing is sent until the session commits (the listener
    below), and a rollback drops it, so a receiver never hears about an action
    that did not happen. The payload carries the action and ids only, never
    scores, emails, names or vote details: a receiver that wants more fetches
    it through the API with a key."""
    if action in NOTIFY_TOPICS:
        return
    # no_autoflush: record() is called with the action's own rows still pending,
    # and flushing them here would move their errors out of the caller's commit.
    with session.no_autoflush:
        event_id = _event_id_for(session, entity_type, entity_id, detail)
        if event_id is None:
            return
        subscriptions = session.exec(
            select(WebhookSubscription).where(
                WebhookSubscription.event_id == event_id,
                WebhookSubscription.active == True,  # noqa: E712 -- SQLAlchemy needs `== True`, not `is True`
            )
        ).all()
    if not subscriptions:
        return
    payload: dict[str, Any] = {
        "topic": action,
        "event_id": event_id,
        "issued_at": utcnow().isoformat(),
        "entity_type": entity_type,
        "entity_id": entity_id,
        "delivery_id": _delivery_id(),
    }
    for key, value in detail.items():
        if key.endswith("_id") and isinstance(value, int) and key not in _PRIVATE_ID_KEYS and key != "event_id":
            payload[key] = value
    pending = session.info.setdefault(_PENDING, [])
    pending.extend(
        (sub.url, sub.id, crypto.sign_record({**payload, "delivery_id": _delivery_id()})) for sub in subscriptions
    )


@sa_event.listens_for(OrmSession, "after_commit")
def _send_after_commit(session: OrmSession) -> None:
    for url, subscription_id, signed in session.info.pop(_PENDING, []):
        _submit(url, subscription_id, signed)


@sa_event.listens_for(OrmSession, "after_rollback")
def _drop_after_rollback(session: OrmSession) -> None:
    session.info.pop(_PENDING, None)
