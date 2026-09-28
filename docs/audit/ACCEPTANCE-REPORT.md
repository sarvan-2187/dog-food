# Acceptance report (task 8)

Acceptance run for the integrated branch `claude/eager-darwin-cm9ap0` (tasks 1-8), on
2026-09-28, against the finished code. Every number below comes from a run on this date;
nothing is carried over from earlier reports.

## Verdict

**Accepted.** Every automated suite passes, the official DOGFOOD checker verifies T1
and T2 (7/7), and every DDoS and rate-limit guard behaved as specified against a live
server. Acceptance testing found two gaps, both fixed on this branch before sign-off
(A1, A2 below). One trade-off needs a decision from the owner (see "Open decision").

## Environment

- Backend run the way the Dockerfile runs it: `python -m app.serve` (uvicorn + the
  header-timeout protocol) on Python 3.11, PostgreSQL 16, a fresh database seeded from
  `fixtures/` and the official `fixtures.json`, the built SPA from `web/dist`, and the
  `DEMO_SESSION_TOKENS` from `docker-compose.yml`.
- `docker compose up` itself could not be run: the build container has no Docker daemon.
  The compose file, the Dockerfile's `CMD ["python", "-m", "app.serve"]` and the pinned
  requirements were exercised piece by piece instead: the same command, the same
  environment variables, and the same pinned packages.
- The spec pages at dogfoodhack.com are blocked by the build environment's network
  policy. Spec requirements come from the in-repo copies (`docs/audit/SPEC-COMPLIANCE.md`).

## Results

| Suite | Command | Result |
|---|---|---|
| Official checker | `python3 run.py .dogfood.toml > acceptance-report.txt` | **7/7 PASS, verified T1 T2** (T3/T4 are judged by hand, as the checker says) |
| Backend | `pytest tests/` (fresh test database) | **584 passed** (428 before this work) |
| Frontend unit | `npx vitest run` | **10 passed** |
| Browser E2E | `npx playwright test` (2 workers, `RATE_LIMIT_PER_MINUTE=0`) | **121 passed, 1 skipped** (the skip is the emailed-reset spec, which needs the mail stack; same as before) |
| Dependency audit | `pip-audit -r api/requirements.txt` | **No known vulnerabilities** |
| One real user, limit on | 15 full page loads in 8.8 s from a single browser, anonymous then signed in | 217 requests, **0** refused |

New backend tests by task: DDoS/rate limit and slow-loris `test_protection.py`; logic
`test_logic_fixes.py`; normalization `test_normalization_properties.py`; webhooks/API
`test_webhooks_live.py`; compliance `test_audit_append_only.py`; security
`test_security.py`.

## Live DDoS / rate-limit probes

Two servers on the same code. Server A runs production defaults. Server B has only the
global limit switched off, so each lower-level guard can be seen on its own.

```
Server A: port 8000, production defaults (200/min). The checker has already made 6 counted requests.
P1  250 sequential GET /api/events from one client
    200s: 194, 429s: 56, first 429 at request 195 (6 checker requests + 194 = 200)
    -> 429 Retry-After: 59 X-RateLimit-Limit: 200 X-RateLimit-Remaining: 0
P2  spoofed X-Forwarded-For while limited -> 429
P3  /healthz while limited -> 200
P4  security headers on a 429: {'x-content-type-options': 'nosniff', 'referrer-policy': 'strict-origin-when-cross-origin', 'x-frame-options': 'DENY'}
Server B: port 8001, same code with RATE_LIMIT_PER_MINUTE=0, so each guard is seen on its own.
P5  5 MB JSON body, declared -> 413 b'{"detail": "Request body too large (limit 4096 KB)."}'
P6  5 MB chunked body, no Content-Length -> HTTP/1.1 413 Request Entity Too Large (was 400 before the fix in this branch)
P7  normal login body -> 401
P8  64 KB request head -> HTTP/1.1 400 Bad Request
P9  idle connection, no request -> closed by server after 10.0s
P10 header lines trickled every 0.1s -> cut off after 10.1s
P11 idle keep-alive after a response -> closed after 5.0s
P12 220 idle sockets opened, then 12s later a real request -> 200 (idle sockets were reaped by the header timeout)
```

## Found during acceptance and fixed here

| # | Finding | Fix |
|---|---------|-----|
| A1 | **Slow-loris.** A connection that opened and sent nothing was never closed (probe P9, before the fix: "NOT closed within 30s"). Uvicorn's keep-alive timeout only starts after a first response, and idle sockets count towards `--limit-concurrency`, so ~200 idle sockets from one machine would make the server answer 503 to everyone. Also, `uvicorn[standard]` selects httptools, which ignores the `--h11-max-incomplete-event-size` flag set in task 1. | `api/app/serve.py`: an h11 protocol that closes any connection with no complete request head within 10 s (`HEADER_TIMEOUT_SECONDS`), started as `python -m app.serve`. P9, P10 and P12 above show it working. Tests use real sockets. |
| A2 | **Oversized chunked body answered 400, not 413.** FastAPI turned the middleware's aborted body read into a JSON parse error. | The middleware replaces that response with the 413 (P6). |
| A3 | **Static files had no cache headers**, so every page load re-fetched ~30 fonts, images and scripts, all counting towards the 200/min limit. | `/assets/*` (content-hashed) are cached for a year as immutable, fonts and images for a day, and HTML is always revalidated. |

## Open decision: the limit and shared addresses

The limit is exactly what was asked: 200 requests a minute per client. A signed-in
person has their own allowance. **Anonymous visitors behind one address share one**:
for example, a venue's wifi NAT with many people browsing the public gallery without
signing in. The browser test suite shows the effect: many test accounts at machine
speed from 127.0.0.1 without a warm cache get 429s, which is why it runs with
`RATE_LIMIT_PER_MINUTE=0`.

The settings, all in `docker-compose.yml` / `.env`:
- `RATE_LIMIT_PER_MINUTE` (default 200; 0 = off);
- `TRUST_PROXY_HOPS` behind a proxy, so the limit sees the real visitor;
- `RATE_LIMIT_PER_IP_CEILING` (default 3000), the cap over all accounts from one
  address.

If venue NAT matters, raise the anonymous allowance, or exempt static files from the
count. That is a product decision, so it is left as specified.

## Deliverables on the branch

- `acceptance-report.txt`: the checker's output, regenerated and unedited (only
  change: the old file's UTF-8 byte-order mark is gone).
- `docs/audit/`: `LOGIC-REVIEW.md`, `NORMALIZATION-ANALYSIS.md`,
  `WEBHOOKS-AND-API.md`, `SPEC-COMPLIANCE.md`, `SECURITY-AUDIT.md`, and this report.
