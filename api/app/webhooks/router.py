"""Webhook subscription CRUD (PLAN.md Phase 7.3). Organizer/admin only --
a webhook receives everything about an event's lifecycle, so minting one is
exactly the kind of control a participant or judge must never have."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, require_role
from ..db import get_session
from ..events.models import Event
from ..ratelimit import webhook_test_limiter
from .models import WebhookSubscription
from .. import crypto
from ..timeutil import utcnow
from .service import _deliver, _delivery_id, blocked_reason
from .targets import refusal

router = APIRouter(tags=["webhooks"])

MAX_WEBHOOKS_PER_EVENT = 10
ORGANIZER = (Role.organizer, Role.admin)


class WebhookCreate(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def url_format(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("Webhook URL must start with http:// or https://.")
        if len(v) > 500:
            raise ValueError("Webhook URL must be 500 characters or fewer.")
        # No DNS lookup at validation time; delivery re-checks with one.
        if reason := blocked_reason(v, resolve=False):
            raise ValueError(reason)
        return v


class WebhookPublic(BaseModel):
    id: int
    url: str
    active: bool
    last_status: str
    created_at: datetime


def _event_or_404(session: Session, event_id: int) -> Event:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    return event


@router.get("/api/events/{event_id}/webhooks", response_model=list[WebhookPublic])
def list_webhooks(
    event_id: int,
    _: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> list[WebhookSubscription]:
    _event_or_404(session, event_id)
    return list(session.exec(select(WebhookSubscription).where(WebhookSubscription.event_id == event_id)))


@router.post("/api/events/{event_id}/webhooks", response_model=WebhookPublic, status_code=status.HTTP_201_CREATED)
def create_webhook(
    event_id: int,
    payload: WebhookCreate,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> WebhookSubscription:
    _event_or_404(session, event_id)
    existing = list(session.exec(select(WebhookSubscription).where(WebhookSubscription.event_id == event_id)))
    if any(w.url == payload.url for w in existing):
        raise HTTPException(status.HTTP_409_CONFLICT, "This event already sends webhooks to that URL.")
    if len(existing) >= MAX_WEBHOOKS_PER_EVENT:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"An event can have at most {MAX_WEBHOOKS_PER_EVENT} webhooks. Delete one first."
        )
    if problem := refusal(payload.url):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    webhook = WebhookSubscription(event_id=event_id, url=payload.url, created_by_id=user.id)
    session.add(webhook)
    session.flush()
    record(session, "webhook.created", actor=user, entity_type="event", entity_id=event_id, webhook_id=webhook.id)
    session.commit()
    session.refresh(webhook)
    return webhook


@router.delete("/api/events/{event_id}/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    event_id: int,
    webhook_id: int,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> None:
    """Deletes rather than merely deactivates: an organizer removing a leaked
    URL should stop deliveries immediately and for good, not leave a row
    around that some future feature might accidentally reactivate."""
    webhook = session.get(WebhookSubscription, webhook_id)
    if not webhook or webhook.event_id != event_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such webhook on this event.")
    # Deleted and flushed before the audit entry is recorded: record() also
    # queues a webhook delivery to the event's active subscriptions, and the
    # removed URL must not be sent even this one last payload.
    session.delete(webhook)
    session.flush()
    record(session, "webhook.deleted", actor=user, entity_type="event", entity_id=event_id, webhook_id=webhook_id)
    session.commit()


class WebhookTestResult(BaseModel):
    id: int
    last_status: str


@router.post("/api/events/{event_id}/webhooks/{webhook_id}/test", response_model=WebhookTestResult)
def test_webhook(
    event_id: int,
    webhook_id: int,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> WebhookTestResult:
    """Send one signed `webhook.test` delivery now and report how it went, so an
    organizer wiring up an integration doesn't have to wait for a real action."""
    webhook = session.get(WebhookSubscription, webhook_id)
    if not webhook or webhook.event_id != event_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such webhook on this event.")
    allowed, retry_after = webhook_test_limiter.check(f"webhook-test:{user.id}")
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"That's a lot of test pings - try again in about {max(1, round(retry_after))} seconds.",
        )
    payload = {
        "topic": "webhook.test",
        "event_id": event_id,
        "issued_at": utcnow().isoformat(),
        "delivery_id": _delivery_id(),
        "webhook_id": webhook_id,
    }
    _deliver(webhook.url, webhook.id, crypto.sign_record(payload), session=session)
    session.refresh(webhook)
    return WebhookTestResult(id=webhook.id, last_status=webhook.last_status)
