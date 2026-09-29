"""Denial-of-service hardening at the application edge (pure ASGI).

What one Uvicorn process can do on its own, with no external service
(PLAN.md: nothing hosted, `docker compose up` works offline):

- **Body cap.** A request body over MAX_BODY_BYTES is refused with 413 before
  the app reads it. Content-Length is checked up front, and chunked bodies are
  counted as they stream in, so a client cannot dodge the cap by leaving the
  header out.
- **Load shedding.** At most MAX_IN_FLIGHT requests are handled at once; the
  next one gets an immediate 503 with Retry-After instead of queueing behind a
  flood until every request times out. Cheap refusals keep the process alive.
- **Deadline.** A request that has not started its response within
  REQUEST_TIMEOUT_SECONDS gets a 504, so slow handlers cannot pile up.
- **Security headers** that cost nothing and close off whole classes of abuse
  (MIME sniffing, referrer leaks).

Slow-loris style attacks (headers trickled in byte by byte, idle keep-alive
sockets) are handled below the app by Uvicorn's own limits, set in the
Dockerfile: --limit-concurrency, --timeout-keep-alive, --backlog and
--h11-max-incomplete-event-size.

The honest limit: no application can make itself immune to a volumetric
attack that saturates the network link before a request ever reaches it.
That needs an upstream edge (a CDN/WAF such as Cloudflare, or the host's own
DDoS protection). docs/THREAT-MODEL.md says so; this module makes sure that
whatever does reach the process is refused as cheaply as possible.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

log = logging.getLogger("hackflow.protection")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


# Uploads are capped at 5 MB by storage.service; leave room for multipart framing.
MAX_BODY_BYTES = _env_int("MAX_BODY_BYTES", 6 * 1024 * 1024)
# JSON bodies are small forms; an event import is the largest legitimate one.
MAX_JSON_BODY_BYTES = _env_int("MAX_JSON_BODY_BYTES", 4 * 1024 * 1024)
MAX_IN_FLIGHT = _env_int("MAX_IN_FLIGHT", 100)
REQUEST_TIMEOUT_SECONDS = float(_env_int("REQUEST_TIMEOUT_SECONDS", 30))

# Liveness must answer even while the app is shedding load, or the orchestrator
# restarts a healthy-but-busy container in the middle of an attack.
EXEMPT_PATHS = frozenset({"/healthz"})


class BodyTooLarge(Exception):
    pass


async def send_json_error(send, status: int, detail: str, headers: "list[tuple[bytes, bytes]] | None" = None) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *(headers or []),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _body_limit_for(scope) -> int:
    for name, value in scope.get("headers", []):
        if name == b"content-type":
            if value.split(b";", 1)[0].strip().lower() == b"application/json":
                return MAX_JSON_BODY_BYTES
            break
    return MAX_BODY_BYTES


class ProtectionMiddleware:
    """Body cap, load shedding and a per-request deadline, in that order."""

    def __init__(self, app, *, max_in_flight: "int | None" = None, timeout: "float | None" = None) -> None:
        self.app = app
        self.max_in_flight = max_in_flight if max_in_flight is not None else MAX_IN_FLIGHT
        self.timeout = timeout if timeout is not None else REQUEST_TIMEOUT_SECONDS
        self.in_flight = 0

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        limit = _body_limit_for(scope)
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    await send_json_error(send, 400, "Invalid Content-Length header.")
                    return
                if declared > limit:
                    await send_json_error(send, 413, f"Request body too large (limit {limit // 1024} KB).")
                    return
                break

        if self.in_flight >= self.max_in_flight:
            log.warning("shedding load: %d requests in flight", self.in_flight)
            await send_json_error(
                send, 503, "The server is busy right now - try again in a few seconds.", [(b"retry-after", b"5")]
            )
            return

        received = 0
        too_large = False

        async def limited_receive():
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    too_large = True
                    raise BodyTooLarge()
            return message

        started = asyncio.Event()

        async def tracking_send(message):
            # A framework may catch BodyTooLarge while reading the body and
            # answer with its own error (FastAPI: a 400 "error parsing the
            # body"). The real reason is the size, so the client gets the 413.
            if too_large:
                if message["type"] == "http.response.start" and not started.is_set():
                    started.set()
                    await send_json_error(send, 413, f"Request body too large (limit {limit // 1024} KB).")
                return
            if message["type"] == "http.response.start":
                started.set()
            await send(message)

        self.in_flight += 1
        try:
            handler = asyncio.ensure_future(self.app(scope, limited_receive, tracking_send))
            waiter = asyncio.ensure_future(started.wait())
            # The deadline covers the time to a first response byte only: once
            # the response has started, background tasks (webhooks, email) that
            # FastAPI runs after it are left to finish.
            await asyncio.wait({handler, waiter}, timeout=self.timeout, return_when=asyncio.FIRST_COMPLETED)
            waiter.cancel()
            if not handler.done() and not started.is_set():
                handler.cancel()
                log.warning("request timed out: %s %s", scope.get("method"), scope.get("path"))
                await send_json_error(send, 504, "The request took too long and was stopped.")
                return
            try:
                await handler
            except BodyTooLarge:
                if not started.is_set():
                    await send_json_error(send, 413, f"Request body too large (limit {limit // 1024} KB).")
        finally:
            self.in_flight -= 1


class SecurityHeadersMiddleware:
    """Headers every response gets. frame_policy in main.py owns the framing ones."""

    HEADERS = [
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"cross-origin-opener-policy", b"same-origin"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
    ]

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # HSTS only on HTTPS (as seen after --proxy-headers): browsers ignore it
        # over plain HTTP anyway, and localhost must stay reachable over http.
        https = scope.get("scheme") == "https"
        framable = scope.get("path", "").startswith("/embed/")

        async def with_headers(message):
            if message["type"] == "http.response.start":
                present = {name.lower() for name, _ in message.get("headers", [])}
                extra = [(n, v) for n, v in self.HEADERS if n not in present]
                # Refusals sent before a route runs (413/429/503) skip main.py's
                # frame_policy; they are never framable either. The widget is.
                if not framable and b"x-frame-options" not in present:
                    extra.append((b"x-frame-options", b"DENY"))
                if https and b"strict-transport-security" not in present:
                    extra.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        await self.app(scope, receive, with_headers)


class TrustedProxyMiddleware:
    """Take the client address from X-Forwarded-For only as far as trusted
    proxies vouch for it.

    Behind a platform proxy (Render, a load balancer) every connection comes
    from the proxy, so per-IP limits would lump all visitors together. Uvicorn's
    FORWARDED_ALLOW_IPS="*" is not the answer: it takes the LEFTMOST entry,
    which the client writes itself, so anyone could pick their own address and
    step around every per-IP limit. Each proxy appends the address it saw, so
    with TRUST_PROXY_HOPS=N the Nth entry from the RIGHT is the one the
    outermost trusted proxy recorded, and nothing the client sends can move it.

    Unset or 0 (the default, and right for `docker compose up`, where browsers
    connect directly): the header is ignored entirely.
    """

    def __init__(self, app, hops: "int | None" = None) -> None:
        self.app = app
        self.hops = hops if hops is not None else _env_int("TRUST_PROXY_HOPS", 0)

    async def __call__(self, scope, receive, send) -> None:
        if self.hops > 0 and scope["type"] in ("http", "websocket"):
            forwarded = [
                v.decode("latin-1") for n, v in scope.get("headers", []) if n == b"x-forwarded-for"
            ]
            hops = [h.strip() for h in ",".join(forwarded).split(",") if h.strip()]
            if len(hops) >= self.hops:
                port = scope["client"][1] if scope.get("client") else 0
                scope = {**scope, "client": (hops[-self.hops], port)}
        await self.app(scope, receive, send)
