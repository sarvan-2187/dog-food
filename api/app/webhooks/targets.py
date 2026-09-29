"""Where a webhook may be sent (SSRF guard).

A webhook URL is chosen by an organizer, but the POST is made by the server,
from inside its network. Without a check, an organizer account (or anyone who
steals one, or an API key) can aim deliveries at things only the server can
reach: the database on db:5432, a cloud metadata service on 169.254.169.254,
an admin panel on localhost. The delivered/failed status then works as a port
scanner for the internal network.

So the host must resolve only to public (globally routable) addresses. It is
checked when the webhook is created and again before every delivery, because
DNS can change in between. WEBHOOK_ALLOW_PRIVATE=1 lifts the rule for an
install whose receivers really are on the local network (and for local
testing).

Residual, documented in THREAT-MODEL.md: a DNS name that answers with a public
address to this check and a private one a moment later, when httpx connects
(DNS rebinding), is not caught.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlsplit


def allow_private() -> bool:
    return os.getenv("WEBHOOK_ALLOW_PRIVATE", "").strip().lower() in ("1", "true", "yes")


def _resolve(host: str, port: int) -> list[str]:
    """Seam for tests, which must not depend on DNS."""
    return [info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def refusal(url: str) -> "str | None":
    """Why this URL may not receive webhooks, or None if it may."""
    try:
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        return "Webhook URL is not a valid URL."
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "Webhook URL must be an http:// or https:// address with a host."
    if parts.username or parts.password:
        return "Webhook URL must not contain a username or password."
    if allow_private():
        return None
    try:
        addresses = _resolve(parts.hostname, port)
    except (OSError, UnicodeError):
        return f"Webhook host {parts.hostname!r} could not be resolved."
    if not addresses:
        return f"Webhook host {parts.hostname!r} could not be resolved."
    if not all(_is_public(a) for a in addresses):
        return (
            "Webhook URL points at a private, loopback or link-local address, which the server "
            "will not call. Set WEBHOOK_ALLOW_PRIVATE=1 if your receiver really is on the local network."
        )
    return None
