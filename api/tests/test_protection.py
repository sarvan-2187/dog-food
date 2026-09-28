"""DoS hardening (app/protection.py, bounded limiter memory, register throttle).

The middleware tests wrap a tiny stand-alone app, so they exercise the ASGI
layer on its own without a database."""
import asyncio

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.protection import ProtectionMiddleware, SecurityHeadersMiddleware
from app.ratelimit import TokenBucketLimiter


def _app(**kwargs) -> FastAPI:
    inner = FastAPI()

    @inner.post("/echo")
    async def echo(request: Request) -> dict:
        return {"size": len(await request.body())}

    @inner.get("/slow")
    async def slow() -> dict:
        await asyncio.sleep(2)
        return {"ok": True}

    @inner.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    inner.add_middleware(ProtectionMiddleware, **kwargs)
    inner.add_middleware(SecurityHeadersMiddleware)
    return inner


def test_small_body_passes():
    r = TestClient(_app()).post("/echo", content=b"x" * 100, headers={"content-type": "text/plain"})
    assert r.status_code == 200
    assert r.json() == {"size": 100}


def test_declared_oversized_body_is_refused_before_reading(monkeypatch):
    monkeypatch.setattr("app.protection.MAX_BODY_BYTES", 1024)
    r = TestClient(_app()).post("/echo", content=b"x" * 2048, headers={"content-type": "text/plain"})
    assert r.status_code == 413


def test_json_bodies_have_their_own_cap(monkeypatch):
    monkeypatch.setattr("app.protection.MAX_JSON_BODY_BYTES", 512)
    r = TestClient(_app()).post("/echo", content=b"{" + b" " * 1000 + b"}", headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_chunked_body_without_length_is_counted(monkeypatch):
    monkeypatch.setattr("app.protection.MAX_BODY_BYTES", 1024)

    def chunks():
        for _ in range(10):
            yield b"x" * 512

    r = TestClient(_app()).post("/echo", content=chunks(), headers={"content-type": "text/plain"})
    assert r.status_code == 413


def test_invalid_content_length_is_rejected():
    app = _app()
    sent: list = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/echo", "headers": [(b"content-length", b"abc")]}
    asyncio.run(ProtectionMiddleware(app)(scope, receive, send))
    assert sent[0]["status"] == 400


def test_load_is_shed_with_503_when_saturated():
    middleware = ProtectionMiddleware(_app(), max_in_flight=0)
    sent: list = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "GET", "path": "/slow", "headers": []}
    asyncio.run(middleware(scope, receive, send))
    assert sent[0]["status"] == 503
    assert (b"retry-after", b"5") in sent[0]["headers"]


def test_health_check_is_never_shed():
    r = TestClient(_app(max_in_flight=0)).get("/healthz")
    assert r.status_code == 200


def test_slow_request_times_out_with_504():
    r = TestClient(_app(timeout=0.2)).get("/slow")
    assert r.status_code == 504


def test_in_flight_counter_returns_to_zero():
    inner = FastAPI()

    @inner.get("/ok")
    def ok() -> dict:
        return {}

    middleware = ProtectionMiddleware(inner)
    client = TestClient(middleware)
    for _ in range(5):
        assert client.get("/ok").status_code == 200
    assert middleware.in_flight == 0


def test_security_headers_are_set():
    r = TestClient(_app()).post("/echo", content=b"", headers={"content-type": "text/plain"})
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "strict-origin" in r.headers["referrer-policy"]
    assert r.headers["cross-origin-opener-policy"] == "same-origin"


def test_real_app_has_security_headers(client):
    r = client.get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


# --- limiter memory --------------------------------------------------------

def test_limiter_memory_is_bounded_under_key_spraying():
    limiter = TokenBucketLimiter(capacity=5, per_seconds=60.0, max_keys=100)
    for i in range(10_000):
        limiter.check(f"ip-{i}", now=1000.0)
    assert len(limiter) <= 100


def test_limiter_prunes_idle_buckets_first():
    limiter = TokenBucketLimiter(capacity=2, per_seconds=60.0, max_keys=3)
    limiter.check("busy", now=0.0)
    limiter.check("busy", now=0.0)  # empty: must be kept
    limiter.check("idle-1", now=0.0)
    limiter.check("idle-2", now=0.0)
    # 120s later the idle ones have refilled; "busy" was just used again.
    limiter.check("busy", now=119.0)
    limiter.check("new", now=120.0)
    assert limiter.peek("busy", now=120.0)[0] is True
    assert len(limiter) <= 3


# --- register throttle -----------------------------------------------------

def test_register_is_throttled_per_ip(client):
    from app.ratelimit import register_ip_limiter

    for i in range(register_ip_limiter.capacity):
        r = client.post(
            "/api/auth/register",
            json={"email": f"flood{i}@example.com", "password": "correct-horse-battery", "name": "Flood Test"},
        )
        assert r.status_code == 201, r.text
    r = client.post(
        "/api/auth/register",
        json={"email": "flood-last@example.com", "password": "correct-horse-battery", "name": "Flood Test"},
    )
    assert r.status_code == 429
    assert "Retry-After" in r.headers


# --- global 200 requests/minute limit (app/request_limit.py) ---------------

from app import request_limit  # noqa: E402
from app.request_limit import SlidingWindowLimiter  # noqa: E402


def test_default_limit_is_200_per_minute():
    assert request_limit.REQUESTS_PER_MINUTE == 200
    assert request_limit.client_limiter.limit == 200
    assert request_limit.WINDOW_SECONDS == 60.0


def test_sliding_window_allows_exactly_200_in_any_minute():
    limiter = SlidingWindowLimiter(200, 60.0)
    t = 0.0
    allowed = 0
    # Spread 1000 attempts over 3 minutes: never more than 200 in any 60s span.
    times = []
    for i in range(1000):
        t = i * 0.18
        ok, _, _ = limiter.hit("c", now=t)
        if ok:
            allowed += 1
            times.append(t)
    for i, start in enumerate(times):
        in_window = sum(1 for x in times[i:] if x < start + 60.0)
        assert in_window <= 200


def test_burst_then_refusal_then_recovery():
    limiter = SlidingWindowLimiter(200, 60.0)
    for i in range(200):
        assert limiter.hit("c", now=10.0)[0]
    ok, remaining, retry = limiter.hit("c", now=10.0)
    assert (ok, remaining) == (False, 0)
    assert retry == pytest.approx(60.0)
    # Refused attempts are not recorded, so retrying does not extend the block.
    for _ in range(50):
        limiter.hit("c", now=40.0)
    assert limiter.hit("c", now=69.9)[0] is False
    assert limiter.hit("c", now=70.0)[0] is True


def test_token_bucket_would_have_allowed_double():
    """Why a sliding log: a 200-capacity, 200/min bucket admits ~400 in one minute."""
    bucket = TokenBucketLimiter(capacity=200, per_seconds=60.0)
    admitted = sum(bucket.check("c", now=t * 0.1)[0] for t in range(600))
    assert admitted > 350
    window = SlidingWindowLimiter(200, 60.0)
    assert sum(window.hit("c", now=t * 0.1)[0] for t in range(600)) == 200


def test_keys_are_independent():
    limiter = SlidingWindowLimiter(2, 60.0)
    assert limiter.hit("a", now=0)[0] and limiter.hit("a", now=0)[0]
    assert not limiter.hit("a", now=0)[0]
    assert limiter.hit("b", now=0)[0]


def test_sliding_window_memory_is_bounded():
    limiter = SlidingWindowLimiter(5, 60.0, max_keys=50)
    for i in range(5000):
        limiter.hit(f"ip-{i}", now=0.0)
    assert len(limiter) <= 50


def test_ipv6_clients_are_grouped_by_64():
    a = request_limit.ip_key("2001:db8:1:2::1")
    b = request_limit.ip_key("2001:db8:1:2:ffff::9")
    c = request_limit.ip_key("2001:db8:1:3::1")
    assert a == b != c
    assert request_limit.ip_key("::ffff:10.0.0.1") == request_limit.ip_key("10.0.0.1")


def test_real_app_returns_429_after_200_requests(client):
    for i in range(200):
        r = client.get("/api/gallery")
        assert r.status_code != 429, f"request {i + 1} was refused"
    assert r.headers["x-ratelimit-limit"] == "200"
    assert r.headers["x-ratelimit-remaining"] == "0"
    r = client.get("/api/gallery")
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert "200 a minute" in r.json()["detail"]
    # Refusals still carry the security headers.
    assert r.headers["x-content-type-options"] == "nosniff"


def test_health_check_is_not_rate_limited(client):
    for _ in range(205):
        assert client.get("/healthz").status_code == 200


def test_signed_in_users_get_their_own_allowance(client, monkeypatch):
    from app.auth.session import create_session_token

    monkeypatch.setattr(request_limit.client_limiter, "limit", 3)
    for _ in range(3):
        assert client.get("/api/gallery").status_code != 429
    assert client.get("/api/gallery").status_code == 429  # anonymous IP spent
    # Another account behind the same address is counted separately...
    client.cookies.set("session", create_session_token(12345, 0))
    assert client.get("/api/gallery").status_code != 429
    # ...but a forged cookie is not an account, so it falls back to the IP.
    client.cookies.set("session", "forged-value")
    assert client.get("/api/gallery").status_code == 429


def test_per_ip_ceiling_caps_many_accounts(client, monkeypatch):
    from app.auth.session import create_session_token

    monkeypatch.setattr(request_limit.ip_limiter, "limit", 5)
    codes = []
    for uid in range(10):
        client.cookies.set("session", create_session_token(1000 + uid, 0))
        codes.append(client.get("/api/gallery").status_code)
    assert codes.count(429) == 5


def test_limit_can_be_switched_off(client, monkeypatch):
    monkeypatch.setattr(request_limit.client_limiter, "limit", 0)
    for _ in range(250):
        assert client.get("/healthz").status_code == 200
    assert client.get("/api/gallery").status_code != 429
