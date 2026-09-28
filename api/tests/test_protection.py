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
