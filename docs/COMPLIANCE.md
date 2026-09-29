# Compliance check against the DOGFOOD 2026 brief

Each requirement of the brief's tier ladder (T1–T4) and its deliverables is checked here
against the running code, as of 2026-09-29. Where the brief's own words are known (quoted
in `docs/PLAN.md` and the commit history), they are quoted. **Status** is one of:

- **Met**: implemented, enforced on the server, and covered by a test;
- **Met (manual)**: implemented, but the official checker doesn't probe it, so it rests on
  our tests;
- **Partial**: implemented with a stated gap.

The official checker (`run.py`) verifies T1 and T2: **7 of 7 pass**
([`acceptance-report.txt`](../acceptance-report.txt)). T3 and T4 are judged by hand, so the
evidence column below is what an evaluator can check.

## Deliverables

| Requirement | Status | Evidence |
|---|---|---|
| Root files an evaluator opens: `.dogfood.toml`, `acceptance-report.txt`, `docker-compose.yml`, README, ARCHITECTURE, DATA-MODEL, JUDGING, LICENSE | Met | repo root |
| One command to a working, seeded portal | Met | `docker compose up`: schema and seed at boot, no `.env` needed |
| The organizers' `fixtures.json` and `run.py` unchanged and loaded | Met | loaded as `sample-hack-2026` (40 projects, 30 judges, 123 scores); `git log -- fixtures.json run.py` shows only the commit that added them |
| `.dogfood.toml` claims and routes | Met | claims T1–T4, and the checker resolves every route |
| No external services required | Met | email and webhooks are opt-in; with neither, zero outbound calls. The new rate limiter is in-process (no Redis). |

## T1: Core

| Requirement | Status | Evidence |
|---|---|---|
| Accounts and roles (participant / judge / organizer / admin); roles never self-chosen | Met | `auth/router.py` (sign-up is always participant); `test_auth.py`, role matrix |
| Events with **"configurable dates, tracks and prizes"** | Met | Event settings; `PATCH /api/events/{id}`; `test_events.py` |
| Teams via invite link, with a size cap | Met | `teams/router.py`; one team per person per event is a unique index; the cap is now race-safe (SECURITY-AUDIT #11) |
| Submission field set: **"Name, tagline, long description, thumbnail, image gallery, hosted demo video URL, repository URL, live link, tech tags, track, plus organizer-defined custom questions"** | Met | `submissions/schemas.py`, `storage/router.py`, `events/questions.py`; `test_submission_fields.py`. The track is now checked against the event's tracks (L5). |
| Deadline enforced on the server | Met | `_load_open_event`; checker **T1 closed event refuses submissions: PASS**; the legacy image route is now included too (SECURITY-AUDIT #8) |
| Public gallery with search | Met | `GET /api/gallery` (search, track and tag filters); checker **T1 gallery is public: PASS**, **project from fixtures shown: PASS** |

## T2: Judging

| Requirement | Status | Evidence |
|---|---|---|
| **"Judge invitation and assignment"** | Met | single-use invites (`judging/invites.py`); conflict-aware, deterministic assignment (`judging/assignment.py`); `test_judge_invites.py`, `test_judging.py` |
| Weighted rubrics | Met | rubric CRUD; weights must add to 1.0 before assignment; locked after the first score. The weighted total now respects each criterion's scale (L1). |
| Only the assigned judge scores; an organizer can't masquerade as a judge | Met | `require_role(judge)` plus ownership plus track check; `test_role_isolation.py` |
| A judge never sees another judge's scores; participants see none | Met | checker **T2 judge sees own scores / cannot see peer scores / participant blocked: PASS** |
| **"A track judge must never see another track"** | Met | `outside_track()`, `assert_in_track()`; `test_track_judges.py` |
| Normalization across judges, defended in JUDGING.md | Met | per-judge z-scores; uninformative judges are now left out, not averaged in (L2); partial data explicit (L4); analysis in `NORMALIZATION-ANALYSIS.md` |
| Judge progress dashboard | Met | `GET /api/judge/assignments` ("X of Y"), the organizer's progress card, reminders |
| CSV exports (users, submissions, assignments, scores, normalized results) | Met | `scoring/router.py`; checker **T2 csv export works: PASS**. The results CSV gains `informative_judges` and `assigned_judges`. |

## T3: Public

| Requirement | Status | Evidence |
|---|---|---|
| Community voting with configurable access: **open link, email-gated, or authenticated** | Met (manual) | `Event.voting_access`, `voting/voter.py`; `test_voting.py` (36), browser `voting.spec.ts` |
| Results hidden during voting, **in the API response**, not just the UI | Met (manual) | `may_see_results()` → `425`; `test_vote_integrity.py` |
| Randomized ordering, stable within a session | Met (manual) | seeded shuffle in `/api/gallery?order=random`; the default while voting is open |
| Comments | Met (manual) | `voting/router.py`; rate-limited |
| Rate limiting | Met (manual) | per-endpoint limits plus the new global limiter (SECURITY-AUDIT, "Rate limits, all in one place") |
| Duplicate-vote detection | Met (manual) | unique index on `(voter_key, submission_id)` plus fingerprint flags for organizers |
| Audit trail | Met (manual) | `audit/log.py`; `GET /api/audit` (organizer-only, no client write path) |

## T4: Stretch

| Requirement | Status | Evidence |
|---|---|---|
| REST API + OpenAPI docs | Met (manual) | `/docs`, `/openapi.json`; API keys (`auth/api_keys.py`) |
| **Webhooks "covering every action the UI can take"** | **Partial** | Every audited action *in an event* is sent, signed with Ed25519 (`webhooks/service.py`), and now SSRF-guarded, capped and replay-safe. Platform-wide actions (sign-ups, role changes, API keys) belong to no event, and webhooks are per event, so they send nothing. |
| Demonstrated with a real third-party integration | Met (manual) | [Raptor Relay](https://github.com/sarvan-2187/hackflow-third-party): an API key plus verified webhooks, run end to end (ACCEPTANCE-REPORT §4) |
| Certificates, server-rendered, no external service | Met (manual) | reportlab PDF plus an HMAC serial checkable at `/verify`; `test_phase4.py` |
| Bulk import/export: **"leave as easily as they arrived"** | Met (manual) | `export.json` / `import` with teams, members, panel, assignments and scores; all-or-nothing; `test_event_import_people.py` |
| Signed judge participation records (offline keypair) | Met (manual) | `crypto.py` (Ed25519, local key), `/participation-record`, `/api/public-key` |
| Embeddable gallery widget | Met (manual) | `/embed/events/{slug}`: the only frameable path |

## PLAN.md constraints that are easy to break while hardening

| Constraint | Status after this change |
|---|---|
| Exact dependency pins (PLAN.md §5) | No new Python dependency. The middleware uses Starlette, already pinned. The frontend change adds none. |
| Single process, no external services | The rate limiter and body caps are in-process. Redis was deliberately not added (SECURITY-AUDIT residual #2). |
| The acceptance checker still passes against a fresh volume | Yes, 7/7, output identical to the committed report. |
| Role isolation enforced in the API, never by the UI | Unchanged, and extended: draft events' rubrics now 404 (#18). |

## Open items (honest)

1. **T4 webhooks, platform-wide actions**: see the Partial row. A site-wide webhook
   setting would close it. It isn't built because webhooks are configured by an event's
   organizers.
2. **T3 and T4 aren't machine-verified** by the official checker. The evidence is our
   tests (457 backend, 121 browser) and the manual walkthroughs.
