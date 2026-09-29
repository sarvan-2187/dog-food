"""Request-level protection: the layer every request passes before a route runs.

What it does, in the order a request meets it:

1. **Client address.** `client_ip()` is the one place the app decides who a
   request came from. Behind a reverse proxy (Render, Caddy, Cloudflare) the
   socket address is the proxy's, so every visitor would share one rate-limit
   bucket. `TRUSTED_PROXY_HOPS=N` says "N proxies I control sit in front of
   me": the client is then the Nth address from the *right* of
   X-Forwarded-For. Counting from the right matters: the left end is whatever
   the client chose to send, so trusting it would let anyone pick their own
   bucket. The default, 0, ignores the header entirely.

2. **Body size cap.** A request body over its route's cap is refused with 413
   before it is read into memory, whether it declares a Content-Length or
   streams chunks. Uploads get 6 MB (5 MB image + multipart overhead), the event
   import 10 MB, everything else 1 MB - far above any real form.

3. **Generous global rate limit.** Per signed-in account (a verified session
   cookie), or per client address for anonymous traffic, a token bucket of
   `RATE_LIMIT_PER_MINUTE` requests (default 600, i.e. 10 a second sustained,
   with the whole minute's budget available as a burst), and a tighter
   `RATE_LIMIT_WRITES_PER_MINUTE` (default 120) for POST/PUT/PATCH/DELETE. An
   API key gets its own, larger bucket (`RATE_LIMIT_API_KEY_PER_MINUTE`,
   default 1200) so an integration behind a shared NAT is not throttled by its
   neighbours. Static files and /healthz are never counted. A person clicking
   through the app never comes near these; a script flooding the API does.
   Endpoint-specific limits (login, voting, password reset...) still apply on
   top, in ratelimit.py.

4. **Security headers** on every response: nosniff, a strict referrer policy,
   a permissions policy that turns off sensors HackFlow never uses, and HSTS
   when the public address is https.

Pure ASGI (no BaseHTTPMiddleware), so the size cap can wrap `receive` and stop
a streamed body mid-flight. Everything is process-local like the rest of the
rate limiting (ratelimit.py explains why). Volumetric floods that saturate the
network link itself are out of any app's reach; put a CDN or the host's DDoS
protection in front for that (docs/SECURITY-AUDIT.md).
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Awaitable, Callable

from starlette.exceptions import HTTPException as StarletteHTTPException

from .ratelimit import TokenBucketLimiter

Scope = dict
Message = dict
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


TRUSTED_PROXY_HOPS = max(0, _int_env("TRUSTED_PROXY_HOPS", 0))

RATE_LIMIT_PER_MINUTE = _int_env("RATE_LIMIT_PER_MINUTE", 600)
RATE_LIMIT_WRITES_PER_MINUTE = _int_env("RATE_LIMIT_WRITES_PER_MINUTE", 120)
RATE_LIMIT_API_KEY_PER_MINUTE = _int_env("RATE_LIMIT_API_KEY_PER_MINUTE", 1200)

MB = 1024 * 1024
DEFAULT_BODY_LIMIT = 1 * MB
UPLOAD_BODY_LIMIT = 6 * MB
IMPORT_BODY_LIMIT = 10 * MB

# 0 turns a limiter off (e.g. a load test against your own install).
request_limiter = TokenBucketLimiter(capacity=max(1, RATE_LIMIT_PER_MINUTE), per_seconds=60.0)
write_limiter = TokenBucketLimiter(capacity=max(1, RATE_LIMIT_WRITES_PER_MINUTE), per_seconds=60.0)
api_key_limiter = TokenBucketLimiter(capacity=max(1, RATE_LIMIT_API_KEY_PER_MINUTE), per_seconds=60.0)

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Never counted: the health probe and files the browser fetches in bulk.
UNLIMITED_PREFIXES = ("/healthz", "/assets/", "/fonts/", "/favicon", "/media/")


def _header(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers") or ():
        if key == name:
            return value.decode("latin-1")
    return ""


def client_ip_from_scope(scope: Scope) -> str:
    socket_ip = (scope.get("client") or ("unknown", 0))[0] or "unknown"
    if TRUSTED_PROXY_HOPS <= 0:
        return socket_ip
    forwarded = [part.strip() for part in _header(scope, b"x-forwarded-for").split(",") if part.strip()]
    if len(forwarded) >= TRUSTED_PROXY_HOPS:
        return forwarded[-TRUSTED_PROXY_HOPS]
    # Fewer entries than proxies we were told about: the request skipped a
    # proxy (or it is a health check), so the socket is the best we know.
    return socket_ip


def client_ip(request) -> str:
    """The caller's address, proxy-aware. Use this, never request.client.host."""
    return client_ip_from_scope(request.scope)


def body_limit_for(path: str) -> int:
    if path == "/api/events/import":
        return IMPORT_BODY_LIMIT
    if path.startswith("/api/users/me/avatar") or "/submission/image" in path:
        return UPLOAD_BODY_LIMIT
    return DEFAULT_BODY_LIMIT


def _cookie(scope: Scope, name: str) -> str:
    for part in _header(scope, b"cookie").split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


def _session_bucket(scope: Scope) -> str | None:
    """A signed-in browser is counted per account, not per address: a whole
    hackathon venue often shares one public IP, and 200 participants must not
    share one bucket. Only a cookie whose signature verifies counts (an HMAC
    check, no database), so a forged cookie falls back to the address bucket."""
    from .auth.deps import DEMO_SESSION_TOKENS  # local: auth imports ratelimit
    from .auth.session import SESSION_COOKIE_NAME, read_session_token

    token = _cookie(scope, SESSION_COOKIE_NAME)
    if not token:
        return None
    if token in DEMO_SESSION_TOKENS:
        return "demo:" + hashlib.sha256(token.encode()).hexdigest()[:16]
    parsed = read_session_token(token)
    return f"user:{parsed[0]}" if parsed else None


def _api_key_bucket(scope: Scope) -> str | None:
    scheme, _, credential = _header(scope, b"authorization").partition(" ")
    if scheme.lower() == "bearer" and credential.strip():
        # Hashed so the limiter's memory never holds a usable key.
        return "key:" + hashlib.sha256(credential.strip().encode()).hexdigest()[:24]
    return None


async def _reply(send: Send, status: int, detail: str, headers: list[tuple[bytes, bytes]] | None = None) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
            + (headers or []),
        }
    )
    await send({"type": "http.response.body", "body": body})


def _security_headers(path: str, https: bool) -> list[tuple[bytes, bytes]]:
    headers = [
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
        (b"cross-origin-opener-policy", b"same-origin"),
    ]
    if https:
        headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
    return headers


class _BodyTooLarge(StarletteHTTPException):
    """Raised from inside the app while it reads the body, so Starlette's own
    exception handling turns it into a normal 413 JSON response."""

    def __init__(self, limit: int) -> None:
        super().__init__(413, f"Request body is too large (limit {limit // MB} MB).")


class ProtectionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        from .auth.mailer import APP_BASE_URL  # local: mailer reads env at import

        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET")
        https = APP_BASE_URL.startswith("https://")

        # 1. Rate limit (before anything touches the database).
        if not path.startswith(UNLIMITED_PREFIXES):
            key_bucket = _api_key_bucket(scope)
            if key_bucket is not None and RATE_LIMIT_API_KEY_PER_MINUTE > 0:
                checks = [(api_key_limiter, key_bucket)]
            else:
                who = _session_bucket(scope) or f"ip:{client_ip_from_scope(scope)}"
                checks = []
                if RATE_LIMIT_PER_MINUTE > 0:
                    checks.append((request_limiter, who))
                if method in WRITE_METHODS and RATE_LIMIT_WRITES_PER_MINUTE > 0:
                    checks.append((write_limiter, who))
            for limiter, key in checks:
                allowed, retry_after = limiter.check(key)
                if not allowed:
                    wait = max(1, round(retry_after))
                    await _reply(
                        send,
                        429,
                        f"Too many requests from this address - slow down and try again in about {wait} seconds.",
                        [(b"retry-after", str(wait).encode())] + _security_headers(path, https),
                    )
                    return

        # 2. Body size cap: refuse a declared oversize body outright...
        limit = body_limit_for(path)
        declared = _header(scope, b"content-length")
        if declared.isdigit() and int(declared) > limit:
            await _reply(send, 413, f"Request body is too large (limit {limit // MB} MB).", _security_headers(path, https))
            return

        # ...and stop a streamed one the moment it passes the cap.
        received = 0

        async def capped_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge(limit)
            return message

        started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                existing = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in _security_headers(path, https) if k not in existing]
                message = {**message, "headers": list(message.get("headers", [])) + extra}
            await send(message)

        try:
            await self.app(scope, capped_receive, send_with_headers)
        except _BodyTooLarge:
            if not started:
                await _reply(send, 413, f"Request body is too large (limit {limit // MB} MB).")


def reset() -> None:
    for limiter in (request_limiter, write_limiter, api_key_limiter):
        limiter.reset()
