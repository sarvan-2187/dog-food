# Security audit (task 7)

Scope: the whole backend (`api/app`), deployment files (`api/Dockerfile`,
`docker-compose.yml`, `render.yaml`), and the dependency trees of `api/` and `web/`.
Method: a manual read of every module for injection, authn/authz, session, crypto,
SSRF, data-exposure and file-handling issues. Then `pip-audit` and `npm audit`,
then the `security-review` skill on the full branch diff (tasks 1-7). Each fix has
a test in `api/tests/test_security.py` unless noted.

## Findings and fixes

| # | Severity | Finding | Fix |
|---|---|---|---|
| S1 | **High** | **Forgeable sessions by default.** With `SESSION_SECRET` unset, sessions, email-verification links, voter cookies and certificate serials were signed with the hard-coded `"dev-only-not-a-real-secret"`, and `docker-compose.yml` set that same published value. Anyone could mint a cookie for any user id, organizer and admin included. | No fallback: when unset, a random 48-byte secret is generated on first boot and kept (mode 0600) in `KEYS_DIR`, so it survives restarts. Compose no longer sets one. A published value logs a warning. `certificate.py` shares the one secret. |
| S2 | **High** | **Vulnerable dependencies.** Starlette 0.41.3 (via FastAPI 0.115.6) had published advisories, including multipart parsing and `FileResponse` Range-header DoS. `python-multipart` 0.0.20, `cryptography` 44.0.0 and `pytest` 8.3.4 also had advisories. The web app's `react-router-dom` 6.28.0 had high-severity open-redirect/XSS advisories. | FastAPI 0.141.1 (Starlette 1.7.0), python-multipart 0.0.32, cryptography 50.0.1, pytest 9.0.3 (pytest-asyncio 1.4.0), react-router-dom 6.30.6. `pip-audit -r requirements.txt`: no known vulnerabilities. The whole suite passes on the new stack. |
| S3 | **Medium** | **SSRF through webhooks.** An organizer, a stolen organizer session, or an API key could point a webhook at `http://db:5432`, `http://169.254.169.254/` (cloud metadata) or `localhost`. The delivered/failed status then worked as an internal port scanner. | `webhooks/targets.py`: only http/https, no credentials in the URL, and every resolved address must be globally routable (IPv4-mapped IPv6 unwrapped). Checked at creation (422) and again before every delivery. Redirects are never followed. `WEBHOOK_ALLOW_PRIVATE=1` opts in for LAN receivers. |
| S4 | **Medium** | **CSV formula injection.** Participants control project titles, team names, answers, comments and display names. A title like `=HYPERLINK(...)` ran as a formula when an organizer opened an export in Excel, LibreOffice or Sheets. | Text cells starting with `= + - @ TAB CR` are prefixed with `'` (OWASP). Numbers are untouched. |
| S5 | **Medium** | **PII over-exposure.** `GET /api/events/{id}/export/users.csv` listed every account on the platform (names, emails, roles), not the event's people, so any organizer could download everyone's email address. | Scoped to the event's team members, judge panel and assigned judges. |
| S6 | **Medium** | **Session cookies without `Secure`.** On an HTTPS deployment the session and voter cookies could still be sent over plain HTTP. | `Secure` whenever `APP_BASE_URL` is https (`COOKIE_SECURE=1/0` overrides). HSTS is sent on HTTPS requests. |
| S7 | Medium | **Spoofable client IP behind a proxy** (found by the `security-review` pass in this branch's own task-2 change). `FORWARDED_ALLOW_IPS="*"` makes uvicorn take the leftmost `X-Forwarded-For` entry, which the client writes, so per-IP limits (login, sign-up, the 200/min limit) could be dodged on Render. | `TrustedProxyMiddleware`: `X-Forwarded-For` is ignored unless `TRUST_PROXY_HOPS=N`, and then only the Nth-from-right entry (the one the trusted proxy appended) is used. `render.yaml` sets 1. |
| S8 | Low | The Ed25519 private key was written with the default umask (world-readable). | Created 0600 (`O_EXCL`). |
| S9 | Low | Passwords over 72 bytes were silently truncated by bcrypt, so two long passwords with the same first 72 bytes were the same password. | New passwords over 72 bytes are refused with a clear message. |
| S10 | Low | `read_session_token` trusted the shape of a validly signed payload. | It requires `{"user_id": int}`. |
| S11 | Low | Early refusals (413/429/503), sent before a route runs, had no `X-Frame-Options`. | Added, except under `/embed/`, which is meant to be framed. |

Also from this branch: DoS hardening and the 200/min limit (tasks 1-2, THREAT-MODEL
entry 32), the audit log made append-only in the database (task 6), and webhook
payloads carrying a `delivery_id` plus a documented instruction to pin the public
key (task 5).

## Checked and found sound

- **SQL injection:** every query goes through the ORM or bound parameters. The only
  `text()` SQL is static DDL.
- **Path traversal:** the SPA catch-all resolves paths and requires them to stay
  inside `STATIC_DIR`. Checked live: `/../../etc/passwd` and the `%2e%2e` form return
  the SPA shell. Uploads use server-generated keys, are checked against `root`, and are
  served only when a `StoredFile` row claims the key.
- **Uploads:** type allow-list plus magic-byte check, 5 MB cap, now also bounded by
  the body limit before parsing.
- **XSS:** React escapes by default. The embed widget escapes every field (test).
  Links are http/https only.
- **Authorization:** `require_role()` everywhere plus ownership checks. The existing
  66-case role matrix passes, and the new route sweep confirms that no route answers
  an anonymous write and none returns a 5xx for any role.
- **Secrets:** API keys and reset tokens are stored as SHA-256 only; tokens come from
  `secrets`.
- **Open redirect:** the verification redirects go to fixed paths.

## `security-review` skill result

Run on the full branch diff (tasks 1-7). No vulnerabilities at or above the report
threshold (confidence ≥ 8). Its one note below the threshold, the spoofable
`X-Forwarded-For` (S7), was fixed anyway.

## Accepted residual risks

- **DNS rebinding:** a name that resolves publicly for the check and privately a
  moment later, when httpx connects, is not caught (documented in `webhooks/targets.py`).
- **Logout** clears the cookie but does not revoke it server-side. A copied cookie
  stays valid until it expires (7 days) or the password changes, which bumps
  `session_version`.
- **react-router 6.x:** two moderate advisories remain. Fixing them needs the v7 major.
  One concerns SSR hydration, which this SPA does not use. The other concerns
  backslash URLs passed to `<Link>` or `navigate`, and the app only navigates to its
  own route constants.
- **`DEMO_SESSION_TOKENS`** in `docker-compose.yml` are fixed organizer, judge and
  participant sessions for the acceptance checker. They are demo only, and the file
  says to delete them on a real deployment.
- **Build-time dev dependencies** (Vite/Vitest/esbuild dev-server advisories) do not
  ship: the runtime image contains only the built static files.
