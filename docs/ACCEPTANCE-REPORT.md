# Acceptance report: 2026-09-29

This covers every check run against the final code of this change. HackFlow was started
fresh (empty database, fixtures seeded at boot, built SPA served by the API), and each
suite below was run against it. Raw outputs are summarized. Commands are given so anyone
can re-run them.

**Verdict: accepted.** The official checker is 7/7. There are 588 automated tests across
three suites, all passing (1 browser spec skipped by design). The third-party
integration worked end to end, and every security control was confirmed live.

## 1. Official DOGFOOD checker (`run.py`)

```text
T1  gallery is public ................. PASS
T1  project from fixtures shown ....... PASS
T1  closed event refuses submissions .. PASS
T2  judge sees own scores ............. PASS
T2  judge cannot see peer scores ...... PASS
T2  participant blocked ............... PASS
T2  csv export works .................. PASS

claimed T1 T2 T3 T4, verified T1 T2
note: claimed but not verified: T3 T4
```

It was run against a fresh database with `python run.py .dogfood.toml`. The output is
byte-for-byte identical to the committed [`acceptance-report.txt`](../acceptance-report.txt)
apart from the file's leading UTF-8 BOM, so the hardening changed nothing the checker sees.
T3 and T4 have no machine checks in `run.py`. Their evidence is sections 2–4 and
[`COMPLIANCE.md`](COMPLIANCE.md).

## 2. Automated test suites

| Suite | Command | Result | Before this change |
|---|---|---|---|
| Backend (pytest, real Postgres) | `docker compose exec api pytest tests/ -q` | **457 passed**, 0 failed | 428 passed |
| Frontend unit (Vitest) | `cd src/web && npm test` | **10 passed** | 10 passed |
| Frontend typecheck | `cd src/web && npx tsc --noEmit` | **clean** | clean |
| Browser E2E (Playwright, Chromium) | `cd src/web && npx playwright test` | **121 passed, 1 skipped** | 121 passed, 1 skipped |
| Raptor Relay (node:test) | `npm test` in hackflow-third-party | **5 passed** | n/a (new) |

The skipped browser spec is the emailed password-reset flow. It needs the Mailpit inbox
(`docker-compose.mail.yml`) and skips itself otherwise, as before.

The 29 new backend tests:

| File | New tests | Covers |
|---|---|---|
| `test_protection.py` | 15 | global limit and `Retry-After`; health exemption; write bucket; API-key bucket; per-account keying (shared NAT); forged-cookie fallback; limiter memory cap; proxy-address trust (off and on); 413 body cap; security headers; email case; sign-up throttle; track validation; frozen legacy upload |
| `test_webhooks.py` | 9 | 6 private or internal targets refused; delivery-time re-check (`blocked`); per-event cap and dedupe; signed test ping with headers |
| `test_scoring.py` | 5 | uninformative judges don't move rank; entry with only uninformative judges; float-noise spread; weights across different max scores; single-scale total unchanged |

Three existing tests were updated, each for a deliberate behavior change: the
one-uninformative-judge case now expects −1.0 instead of the diluted −0.5; the audited
webhook payload gains `delivery_id`; and the unreachable-webhook test opts into private
addresses, since `127.0.0.1` is now blocked by default.

**Browser suite under default rate limits.** All 121 specs run with Playwright's parallel
workers from one address. The server log shows **zero `429` responses** across the whole
run, so the limits don't touch real use.

## 3. Live security checks (default settings)

| Check | Expected | Observed |
|---|---|---|
| 2,000 `GET /api/gallery`, 64 in parallel, one address | burst served, rest refused cheaply | 688 × `200`, 1,312 × `429` in 8.9 s; `/healthz` answered in 2 ms right after |
| One 2 MB JSON body to `/api/auth/login` | refused before reading | `413` |
| 12 wrong passwords for one account | throttled after 10 | 10 × `401`, then `429` |
| 25 sign-ups from one address | throttled after 20 | 20 × `201`, then 5 × `429` |
| Webhook to `127.0.0.1`, `localhost`, `169.254.169.254`, `10.x`, `[::1]`, `*.internal` | refused | `422` for each (tests) |
| Forged webhook delivery to Raptor Relay | rejected | `401 {"error":"bad signature"}`, counted on the dashboard |

## 4. Third-party integration, end to end

[Raptor Relay](https://github.com/sarvan-2187/hackflow-third-party) (a separate repo) ran
against the seeded HackFlow, with only an organizer API key:

1. `GET /api/auth/me` with the key: *Alice Organizer, organizer*.
2. `GET /api/public-key`: signing key pinned.
3. Events listed (10), gallery read (40 projects), normalized standings read (top 5 with
   `judges/assigned_judges`).
4. `POST /api/events/10/webhooks`: the relay subscribed itself. `POST .../test`:
   **delivered**.
5. HackFlow then sent `webhook.created`, `webhook.test`, `announcement.posted` (an
   announcement posted *by the relay through the API*) and `event.updated` (a rules edit made
   with the key). **All four verified** against the pinned key, with fresh `issued_at` and
   unique `delivery_id`.
6. A hand-forged `event.results_revealed` was **rejected**.

Screenshot: `docs/screenshots/manual/27-raptor-relay.png`. Walkthrough:
[`USER-MANUAL.md`](USER-MANUAL.md#integrations-api-keys-and-webhooks).

## 5. Normalization on the official fixtures

From `GET /api/events/10/export/results.csv` after the fixes (full analysis in
[`NORMALIZATION-ANALYSIS.md`](NORMALIZATION-ANALYSIS.md)):

- 40 ranked rows; winner Iron Switch (z̄ +1.232). The top 8 are unchanged by the fixes.
- 3 of 30 judges are uninformative and now left out of z̄. 12 ranks move by 1–2 places.
- Rescaling one judge's scores changes normalized z̄ by **0.000000** (raw-mean ranks: 40 of
  40 change).
- Removing any single judge keeps at least 8 of the top 10, and the winner survives 27 of
  30 removals.
- Rubric totals on the fixtures are unchanged by the weighted-total fix (a single 1–5 scale
  with weights adding to 1).

## 6. Documents delivered with this change

| Document | Purpose |
|---|---|
| [`SECURITY-AUDIT.md`](SECURITY-AUDIT.md) | 18 findings with fixes and tests, flood measurements, all rate limits, residual risks |
| [`NORMALIZATION-ANALYSIS.md`](NORMALIZATION-ANALYSIS.md) | Scoring pipeline, 6 logic errors fixed, measured properties, limitations |
| [`FLOW-ANALYSIS.md`](FLOW-ANALYSIS.md) | The 10 stages gate by gate, with tests and findings |
| [`COMPLIANCE.md`](COMPLIANCE.md) | Brief requirement → status → evidence |
| [`USER-MANUAL.md`](USER-MANUAL.md) §7 | API keys, webhooks, signature verification, Raptor Relay walkthrough |
| `THREAT-MODEL.md` | Entries 32–36 added (floods, SSRF, forged or replayed webhooks, spoofed addresses, mass sign-up) |

## 7. Not verified here

- **`docker compose up --build` itself** wasn't run in this environment. The API ran
  under `uvicorn` with the same code, fixtures, environment and seed, against Postgres 16,
  and `docker compose config` validates the edited compose file. The image build steps are
  unchanged.
- **Render deployment** with `TRUSTED_PROXY_HOPS=1` wasn't exercised live. The value must
  match the number of proxies exactly. Too low, and visitors share the innermost proxy's
  bucket, as they all did before this change. Too high, and a client can choose its own
  bucket by sending a fake `X-Forwarded-For`. Check one request's header on the host before
  changing it.
