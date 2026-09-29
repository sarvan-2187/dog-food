"""Global request rate limit: at most 200 requests per minute per client.

Every HTTP request except the health check passes through here, on top of the
tighter per-action limits in ratelimit.py (login, votes, comments, ...).

**Exactly 200 in any 60 seconds.** A token bucket with capacity 200 and a
refill of 200/min lets a client send up to ~400 requests inside one sliding
minute (a full bucket, then its refill). This limiter is a sliding log instead:
it remembers the time of each client's last 200 requests and refuses the next
one until the oldest is a full minute old. The guarantee is exact, and memory
is bounded at 200 timestamps per client and MAX_CLIENTS clients.

**Who is a client.** A signed-in browser is its account (the session cookie's
signature is checked, which needs no database), so a hackathon venue behind
one NAT address does not share a single allowance between a hundred people.
Anyone else (anonymous visitors, API keys, forged or expired cookies) is keyed
by IP address, IPv6 by its /64 so one host cannot rotate through its prefix.
A per-IP ceiling (PER_IP_CEILING, default 3000/min) sits over all of that, so
an attacker who signs up many accounts still cannot multiply their allowance
without bound.

request.client comes from protection.TrustedProxyMiddleware: X-Forwarded-For is
ignored unless TRUST_PROXY_HOPS is set, and then only the entry the trusted
proxy appended is used, so a client cannot pick its own key by sending it.

Set RATE_LIMIT_PER_MINUTE=0 to switch the global limit off (for example, a
load test from a single machine).
"""
from __future__ import annotations

import ipaddress
import json
import os
import threading
import time
from collections import deque
from http.cookies import SimpleCookie


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


REQUESTS_PER_MINUTE = _env_int("RATE_LIMIT_PER_MINUTE", 200)
PER_IP_CEILING = _env_int("RATE_LIMIT_PER_IP_CEILING", 3000)
WINDOW_SECONDS = 60.0
MAX_CLIENTS = _env_int("RATE_LIMIT_MAX_CLIENTS", 20_000)
EXEMPT_PATHS = frozenset({"/healthz"})


class SlidingWindowLimiter:
    """At most `limit` hits per `window` seconds for each key, exactly."""

    def __init__(self, limit: int, window: float = WINDOW_SECONDS, max_keys: int = MAX_CLIENTS) -> None:
        self.limit = limit
        self.window = window
        self.max_keys = max_keys
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, *, now: "float | None" = None) -> tuple[bool, int, float]:
        """Record one request. Returns (allowed, remaining, retry_after_seconds).
        A refused request is not recorded, so hammering while blocked does not
        push the unblock time further out."""
        current = time.monotonic() if now is None else now
        cutoff = current - self.window
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= self.max_keys:
                    self._prune(cutoff)
                hits = deque(maxlen=self.limit)
                self._hits[key] = hits
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, 0, max(0.0, hits[0] - cutoff)
            hits.append(current)
            # Keep the dict in least-recently-used order for _prune.
            self._hits[key] = self._hits.pop(key)
            return True, self.limit - len(hits), 0.0

    def _prune(self, cutoff: float) -> None:
        for key in [k for k, h in self._hits.items() if not h or h[-1] <= cutoff]:
            del self._hits[key]
        if len(self._hits) >= self.max_keys:
            for key in list(self._hits)[: len(self._hits) // 2 + 1]:
                del self._hits[key]

    def __len__(self) -> int:
        return len(self._hits)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


client_limiter = SlidingWindowLimiter(REQUESTS_PER_MINUTE)
ip_limiter = SlidingWindowLimiter(PER_IP_CEILING)


def ip_key(host: str) -> str:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return f"ip:{host}"
    if addr.version == 6:
        if addr.ipv4_mapped is not None:
            return f"ip:{addr.ipv4_mapped}"
        return f"ip6:{ipaddress.ip_network(f'{addr}/64', strict=False).network_address}"
    return f"ip:{addr}"


def _session_user_id(scope) -> "int | None":
    from .auth.session import SESSION_COOKIE_NAME, read_session_token

    for name, value in scope.get("headers", []):
        if name == b"cookie":
            try:
                cookie = SimpleCookie(value.decode("latin-1"))
            except Exception:
                return None
            morsel = cookie.get(SESSION_COOKIE_NAME)
            if morsel is None:
                return None
            parsed = read_session_token(morsel.value)
            return parsed[0] if parsed else None
    return None


def client_key(scope) -> tuple[str, str]:
    """(identity key, IP key) for this request."""
    client = scope.get("client")
    by_ip = ip_key(client[0] if client else "unknown")
    user_id = _session_user_id(scope)
    return (f"user:{user_id}" if user_id is not None else by_ip), by_ip


class RateLimitMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or client_limiter.limit <= 0 or scope.get("path") in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        identity, by_ip = client_key(scope)
        allowed, remaining, retry_after = client_limiter.hit(identity)
        if allowed and identity != by_ip and ip_limiter.limit > 0:
            allowed, _, retry_after = ip_limiter.hit(by_ip)
        limit_headers = [
            (b"x-ratelimit-limit", str(client_limiter.limit).encode()),
            (b"x-ratelimit-remaining", str(remaining if allowed else 0).encode()),
        ]
        if not allowed:
            wait = max(1, int(retry_after + 0.999))
            body = json.dumps(
                {"detail": f"Too many requests - the limit is {client_limiter.limit} a minute. "
                           f"Try again in about {wait} seconds."}
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"retry-after", str(wait).encode()),
                        *limit_headers,
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        async def with_headers(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []), *limit_headers]}
            await send(message)

        await self.app(scope, receive, with_headers)


def reset() -> None:
    client_limiter.reset()
    ip_limiter.reset()
