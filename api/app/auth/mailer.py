"""Outbound email over plain SMTP (PLAN.md Phase 9.3) - stdlib only.

Opt-in exactly like webhooks (Phase 7.3): with SMTP_HOST unset, `enabled` is
False and nothing here ever opens a socket, so a default `docker compose up`
still makes zero runtime network calls (PLAN.md section 1).

Settings are read once at import. Changing them means restarting the api
container; the admin "Email delivery" card says so.
"""
from __future__ import annotations

import logging
import os
import smtplib
import socket
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class MailConfig:
    host: str
    port: int
    security: str  # "starttls" | "ssl" | "none"
    username: str
    password: str
    sender: str

    @property
    def enabled(self) -> bool:
        return bool(self.host)


def _load() -> MailConfig:
    security = os.getenv("SMTP_SECURITY", "").strip().lower() or "starttls"
    if security not in ("starttls", "ssl", "none"):
        log.warning("SMTP_SECURITY=%r is not starttls/ssl/none; using starttls.", security)
        security = "starttls"
    port_default = "465" if security == "ssl" else "587"
    username = os.getenv("SMTP_USERNAME", "").strip()
    return MailConfig(
        host=os.getenv("SMTP_HOST", "").strip(),
        port=int(os.getenv("SMTP_PORT", "").strip() or port_default),
        security=security,
        username=username,
        password=os.getenv("SMTP_PASSWORD", ""),
        sender=os.getenv("SMTP_FROM", "").strip() or (f"HackFlow <{username}>" if "@" in username else "HackFlow <hackflow@localhost>"),
    )


CONFIG = _load()

# Absolute links in emails. Also the one place a deployment names its own URL.
APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip().rstrip("/") or "http://localhost:8000"


class MailError(Exception):
    """A delivery failure, already phrased for an organizer to read."""


def _message(to: str, subject: str, text: str, html: str | None) -> EmailMessage:
    # EmailMessage encodes headers itself, so a crafted display name or subject
    # cannot smuggle in extra headers.
    msg = EmailMessage()
    msg["From"] = CONFIG.sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def send(to: str, subject: str, text: str, html: str | None = None) -> None:
    """Send one message, synchronously. Raises MailError on any failure."""
    send_many([(to, subject, text, html)])


def send_many(messages: list[tuple[str, str, str, str | None]]) -> int:
    """Send (to, subject, text, html) messages over ONE connection - an
    announcement to a 200-person event must not open 200 (PLAN.md 10.11).
    Returns how many were accepted. A refused recipient is skipped; a
    connection-level failure raises MailError."""
    cfg = CONFIG
    if not cfg.enabled:
        raise MailError("Email is not set up on this HackFlow (SMTP_HOST is empty).")
    target = f"{cfg.host}:{cfg.port}"
    sent = 0
    try:
        context = ssl.create_default_context()
        if cfg.security == "ssl":
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=TIMEOUT_SECONDS, context=context)
        else:
            smtp = smtplib.SMTP(cfg.host, cfg.port, timeout=TIMEOUT_SECONDS)
        with smtp:
            if cfg.security == "starttls":
                smtp.starttls(context=context)
            if cfg.username:
                smtp.login(cfg.username, cfg.password)
            for to, subject, text, html in messages:
                try:
                    smtp.send_message(_message(to, subject, text, html))
                    sent += 1
                except smtplib.SMTPRecipientsRefused:
                    if len(messages) == 1:
                        raise
                    log.warning("Email to %s refused by %s; continuing with the rest.", to, target)
        return sent
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError(
            "The mail server rejected the login. Check SMTP_USERNAME and SMTP_PASSWORD - "
            "for Gmail or Outlook this must be an app password, not your normal one."
        ) from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise MailError(f"The mail server refused to deliver to {to}.") from exc
    except smtplib.SMTPNotSupportedError as exc:
        raise MailError(
            f"{target} does not support STARTTLS. Try SMTP_SECURITY=ssl with port 465, "
            "or none only for a local test inbox."
        ) from exc
    except (ssl.SSLError, smtplib.SMTPServerDisconnected) as exc:
        raise MailError(
            f"The secure connection to {target} failed. Port 587 usually needs SMTP_SECURITY=starttls, "
            "port 465 needs ssl."
        ) from exc
    except (socket.gaierror, ConnectionRefusedError, TimeoutError, socket.timeout, OSError) as exc:
        raise MailError(f"Could not reach the mail server at {target}.") from exc
    except smtplib.SMTPException as exc:
        raise MailError(f"The mail server at {target} returned an error: {exc}") from exc


def send_quietly(to: str, subject: str, text: str, html: str | None = None) -> None:
    """For BackgroundTasks: a failure is logged, never raised - the request that
    queued it has already answered, and must not reveal whether it sent."""
    try:
        send(to, subject, text, html)
    except MailError as exc:
        log.warning("Email to %s (%r) not sent: %s", to, subject, exc)


def send_many_quietly(messages: list[tuple[str, str, str, str | None]]) -> None:
    """BackgroundTasks twin of send_many: logs instead of raising."""
    try:
        sent = send_many(messages)
        log.info("Sent %s of %s emails.", sent, len(messages))
    except MailError as exc:
        log.warning("Bulk email not sent (%s messages): %s", len(messages), exc)
