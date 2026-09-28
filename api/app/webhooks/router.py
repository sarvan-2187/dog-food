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
from .models import WebhookSubscription

router = APIRouter(tags=["webhooks"])

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
