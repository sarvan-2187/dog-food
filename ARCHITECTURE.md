# ARCHITECTURE.md — HackFlow

## Shape: a modular monolith, two runtime containers

Everything runs from `docker compose up`, no manual steps, no `.env` to hand-fill (PLAN.md
§1). At runtime there are exactly two containers. An optional third, a local Mailpit test
inbox, is added only by `docker-compose.mail.yml` (see "Password recovery and email"):

```
┌──────────────┐        ┌──────────────────────────────────────────┐
│  db           │◄──────►│  api                                       │
│  postgres:16   │        │  FastAPI + Uvicorn, serving:                │
│  named volume  │        │   - /api/*  (all backend routes)            │
└──────────────┘        │   - /*      (the built React SPA, as static  │
                          │              files — no separate web        │
                          │              container at runtime)          │
                          └──────────────────────────────────────────┘
```

There is no `web` service in `docker-compose.yml`. `api/Dockerfile` is a two-stage build:
stage 1 (`node:20-slim`) runs `npm ci && npm run build` to produce `web/dist`; stage 2
(`python:3.12-slim`) copies that build output in as static files and discards Node
entirely. One image, one process, serving both the API and the SPA shell — the SPA's
catch-all route (`api/app/main.py`) returns `index.html` for any non-API path so client-
side routing survives a hard refresh.

**Why a monolith, not microservices.** There are four roles and roughly a dozen closely
related entities (events, teams, submissions, rubrics, assignments, scores, votes,
comments) that all reference each other and share one transactional boundary — a
submission's deadline check, a rubric's lock-once-scoring-starts rule, and a vote's
duplicate guard all need to see consistent state in one query. Splitting that across
services would mean either distributed transactions or eventual consistency for
guarantees that matter (nobody should be able to score after a rubric changes because two
services disagreed about ordering). A single Postgres database and a single FastAPI
process keep those guarantees cheap and the whole system simple enough to fully audit
(see the Phase 0/1 Audit in PLAN.md) in the time a hackathon actually allows.

## Backend: one Python package per domain

```
api/app/
├── main.py          # FastAPI app entry: lifespan (schema + upgrades + seed), mounts
│                     #   every router, then the SPA static mount + catch-all
├── db.py            # the one engine + get_session(); create_db_and_tables() also runs
│                     #   add_missing_columns(), add_guarded_indexes(), run_backfills()
├── seed.py          # idempotent fixture seeding, run automatically on every boot
├── timeutil.py      # utcnow() / ensure_utc() — the only source of "now" in the app
├── ratelimit.py     # the in-process token bucket, and every limiter the app uses
├── crypto.py        # the Ed25519 signing key (participation records, webhook payloads)
├── auth/            # User model, Role enum, password hashing, versioned session cookies,
│   │                 #   get_current_user(), require_role() — imported everywhere else
│   ├── recovery.py   #   reset links (emailed / organizer-issued / CLI), admin email card
│   ├── mailer.py     #   opt-in SMTP over stdlib smtplib; off unless SMTP_HOST is set
│   ├── admin_users.py #  admin user management: roles, deactivation, integrity warning
│   └── reset_link.py #   break-glass CLI: python -m app.auth.reset_link <email>
├── events/          # Event model + CRUD, draft/publish, public criteria
│   └── announcements.py # organizer announcements (page, dashboards, email, webhook)
├── teams/           # Team + TeamMembership, invites, one-team-per-event, captain actions
├── submissions/     # Submission model, autosave PATCH, links, deadline enforcement,
│                     #   gallery
├── judging/         # Rubric, JudgeAssignment, JudgeInvite, EventJudge, JudgeConflict,
│   │                 #   the assignment algorithm
│   └── event_judges.py # an event's judge panel, progress, removal, reminders, conflicts
├── scoring/         # Score model, normalization pipeline, CSV export, backup, certificates
│   └── awards.py     #   winners: suggestions from the standings, reveal-gated publishing
├── voting/          # Vote + Comment models, duplicate detection
├── storage/         # StorageService + LocalStorage for uploaded images
├── webhooks/        # opt-in signed outbound webhooks
└── audit/           # append-only log writer + query endpoint
```

Each domain package owns its `models.py` (SQLModel table classes), `schemas.py` (request/
response Pydantic models, kept separate from the table models so a response never
accidentally leaks a column like `password_hash`), and `router.py`. Cross-package
dependencies are intentionally shallow and one-directional — e.g. `teams/deps.py`'s
`require_team_member` is imported by `submissions/router.py`, never the reverse — so there
are no import cycles and no domain needs to know about a domain that comes after it in the
phase order.

`require_role()` (in `auth/deps.py`) is the single place role gating is implemented; every
other package imports it rather than writing an inline `if user.role != ...` check. This
is what makes `test_role_isolation.py`'s table-driven matrix meaningful — one dependency
to trust, not N copies that could each drift.

## Frontend: pages consume shared primitives, never re-invent them

```
web/src/
├── components/
│   ├── ui/         # Button, Input, Card, Badge — built once in Phase 0, before any
│   │                #   feature page existed
│   ├── EventTimeline.tsx  # event phase (Upcoming/Open/Judging/Results) + countdown
│   ├── EventSections.tsx  # rules, public criteria, winners, announcements, project links
│   ├── TeamManager.tsx    # leave / rename / remove / captaincy / new invite link
│   ├── JudgePanelCard.tsx # an event's judges and their progress (organizer view)
│   └── AccountRecoveryPanels.tsx # "Help someone sign in" + admin "Email delivery"
│   ├── feedback/    # Toast, Skeleton, EmptyState, ErrorState, InlineStatus — the
│   │                #   loading/empty/error states every screen reuses
│   ├── auth/        # RequireAuth / RequireRole route guards
│   └── layout/      # NavBar (role-aware: an item a role can't use is absent, not
│                     #   disabled)
├── lib/             # api.ts (fetch wrapper, plain-language error surfacing),
│                     #   auth-context.tsx (current user + login/register/logout)
├── styles/           # tokens.ts — the single source of design tokens, mirrored into
│                     #   tailwind.config.ts; nothing else hardcodes a hex or a px value
└── pages/            # one file per screen, each built from the primitives above
```

Design tokens flow one direction: `DESIGN_SYSTEM.md` (derived from `reference_design.pdf`)
→ `web/src/styles/tokens.ts` → `web/tailwind.config.ts`'s `theme.extend`. A component
reaching for a raw hex or an ad-hoc spacing value instead of a token is the one thing the
Phase 5 audit specifically checks for.

## Auth: server-side sessions, not a token the client can forge

Registration and login set an `itsdangerous`-signed, `httponly`, `samesite=lax` cookie
carrying the user id and the account's `session_version`. `get_current_user()` reads and
verifies it on every request that needs identity, and refuses it if the version is stale
or the account is deactivated. There is no JWT, no client-side role claim to trust —
every role check happens against the `role` column read fresh from the database on that
request. Passwords are hashed with `passlib[bcrypt]`; `password_hash` is never part of any
response schema.

Login counts **failed** attempts only: 10 per account and 30 per IP per 15 minutes
(`app/ratelimit.py`). Both buckets are checked *before* the password, so once an account
or address is throttled, even a correct guess is refused. Otherwise someone trying one
password across many accounts could ignore the 429s. An unknown email still runs bcrypt
against a dummy hash, so response time doesn't reveal which emails are registered. A
successful login clears that account's count.

## Deployment / no-network-calls constraint

`docker compose up` builds both images from local Dockerfiles and pulls only
`postgres:16-alpine` and `node:20-slim`/`python:3.12-slim` from the standard registries at
build time. Once running, the api container makes no *required* outbound network calls —
no cloud database, no auth-as-a-service, no external API, no CDN-fetched font or script in
the served app (PLAN.md §1). This is why fonts fall back to the system stack (see
`DESIGN_SYSTEM.md` §3.1) rather than a Google Fonts `<link>`, and why CSV export uses the
Python stdlib `csv` module instead of a hosted export service. There are exactly two
exceptions, both opt-in: outbound webhooks (below), configured per event, and
password-reset email (below), configured per deployment. An install that sets up neither
gets the original zero-outbound-calls behavior unchanged — the test suite asserts that no
SMTP connection is attempted with email off.

## Uploaded images: local disk, no CDN

Submission screenshots and profile avatars are stored on the api container's local disk
behind a `StorageService` interface (`api/app/storage/service.py`), not a cloud bucket —
the same self-hostable/offline constraint that governs everything else in this document.
`save()`/`read()`/`url_for()`/`delete()`/`exists()` is the whole interface; `LocalStorage`
is the only implementation. Keys are server-generated (`uuid4().hex` plus an extension
derived from the validated content-type), never taken from a client-supplied filename, so
there is no path-traversal surface. `StoredFile` (`api/app/storage/models.py`, see
DATA-MODEL.md) tracks ownership; a submission or user has at most one current file, and
uploading a new one deletes the old one rather than accumulating orphans on disk. There is
no CDN: images are served straight from the api container, which is consistent with the
"works fully offline" requirement — a CDN would be a hard external dependency this
platform is specifically built not to need.

## Password recovery and email: opt-in SMTP, hashed single-use links

Every reset link, whether emailed, organizer-issued, or printed by the break-glass CLI, is
one `PasswordReset` row (DATA-MODEL.md) holding only the SHA-256 of a
`secrets.token_urlsafe(32)` token. Links are redeemed through the same two endpoints
(`GET …/preview`, which never consumes the link, and `POST …/redeem`) and the same
`/reset/:token` page (`api/app/auth/recovery.py`). Emailed links expire in 30 minutes;
organizer and CLI links, handed over live, expire in 60. Issuing a new link retires any
earlier unused one for that account.

Sessions are revocable: the signed cookie carries `{user_id, v}`, and `get_current_user`
rejects any cookie whose `v` isn't the account's current `session_version`. Every password
change or reset increments it, which signs the account out everywhere at once. Cookies
signed before this existed have no `v` and read as 0, so the upgrade signed nobody out.

Email is sent by `api/app/auth/mailer.py` using stdlib `smtplib` and `email.message`, with
no SDK and no new dependency. It is read from `SMTP_*` environment variables once at
startup; with `SMTP_HOST` empty it is off, and nothing in the module opens a socket. Reset
and "your password was changed" emails go out through FastAPI `BackgroundTasks`, one
attempt with a 10-second timeout, the same fire-and-forget choice as webhooks. That way a
slow mail server never delays a response, and a response can't reveal whether an account
exists. Failures are logged. `docker-compose.mail.yml` adds a local Mailpit inbox, with
its own version check disabled, for demos and the end-to-end test.

Adding `session_version` to an existing `users` table is handled by
`db.add_missing_columns()`, a short list of `(table, column, ddl)` entries applied at
startup only when `information_schema` says the column is absent. That replaces
`docker compose down -v` as the way to pick up a new column. The check matters:
`ADD COLUMN IF NOT EXISTS` on its own still takes an exclusive table lock on every boot,
which hung the test suite when it was tried.

## Many events, one platform (Phase 10)

Phases 0–8 ran *an* event correctly. Running dozens exposed rules that only break once
several events exist, and those are now enforced in the API, not the UI:

- **Judges belong to events.** Assignment draws only from the event's `event_judges`
  panel. A judge invitation carries an `event_id`, and redeeming it enrols the judge on
  that panel only. Organizers can also add an existing judge by email; that requires an
  account that already has the judge role, so it isn't a second way into the role.
- **One team per person per event.** Checked in `create_team`/`join_team`, and held by a
  unique index on `team_memberships(event_id, user_id)`. `event_id` is stamped onto each
  membership by a SQLAlchemy `before_insert` listener, so no caller can forget it.
- **Judging opens only when submissions close.** Assignment and scoring are refused
  before `end_at`, and a judge's list only includes events whose judging is open. Every
  score is therefore of the version that was actually submitted.
- **Gap-filling assignment.** Existing assignments count toward each submission's `k` and
  each judge's load, and declared conflicts (`judge_conflicts`) join the same-team
  conflict set. Removing a judge and re-running tops submissions back up to `k`, never
  past it. See JUDGING.md.
- **Drafts.** New and imported events start as `status = "draft"`. They're left out of
  lists and the gallery, and return 404 (not 403) to anyone but organizers.
- **Winners** (`scoring/awards.py`) are suggested from the normalised standings, confirmed
  by the organizer, and withheld through the same `may_see_results` gate as the
  standings.

The event phase shown in the UI (Upcoming / Open / Judging / Results) is computed in the
browser from the same `start_at` / `end_at` / `results_hidden_until` the server enforces,
so the page and the API can't disagree.

## Upgrading an existing database without a migration tool

There is still no migration framework. `create_all()` creates missing tables, and three
idempotent steps run after it on every boot (`api/app/db.py`):

1. **`add_missing_columns()`** adds each new column on an existing table, but only after
   `information_schema` confirms it's absent. `ADD COLUMN IF NOT EXISTS` alone takes an
   exclusive table lock every boot, and that hung the test suite behind an open
   transaction.
2. **`add_guarded_indexes()`** creates the one-team-per-event unique index only when the
   existing data already satisfies it. A volume with duplicates from before the rule
   still boots: the duplicates are logged, and the admin **Users** page lists them until
   they're resolved.
3. **`run_backfills()`** fills new columns for old rows: membership event ids, team
   captains, and event-judge panels built from existing assignments.

The result: `docker compose up` on an old volume upgrades it in place, and
`docker compose down -v` is only for wanting a clean slate.

## Outbound webhooks: fire-and-forget, signed, opt-in

An organizer can subscribe an event to a URL (`WebhookSubscription`, DATA-MODEL.md) for
five topics: `submission.submitted`, `assignments.run`, `score.submitted`,
`event.results_revealed`, and `announcement.posted`, so organizer announcements reach a
Discord or Slack channel automatically. `webhooks/service.py`'s `notify()` looks up that event's active
subscriptions and, for each one, schedules delivery via FastAPI `BackgroundTasks` so the
triggering request (a submission, an assignment run, a score, a results read) never waits
on a third party's server. Delivery is single-attempt with no retry queue — a deliberate
scope cut, since a durable retry system is real infrastructure a hackathon-scale platform
does not need. Every payload is signed with the same Ed25519 key already built for judge
participation records (`api/app/crypto.py`), so a receiver can verify authenticity offline
against `GET /api/public-key` without trusting the network path. The `event.results_
revealed` topic fires exactly once per event, guarded by a one-shot flag checked lazily
the next time results are actually read (not by a background scheduler), and gated on
results being *publicly* visible so an organizer's own early access can't trigger it.

## Testing architecture

- **Backend** (`api/tests/`, pytest): a dedicated `dogfood_test` database, with each test
  wrapped in a SQLAlchemy `SAVEPOINT` so a route handler's own `session.commit()` calls
  don't end the outer transaction — the whole test still rolls back cleanly at the end.
- **Frontend unit** (`web/src/**/*.test.ts(x)`, Vitest): pure functions and small
  components, mocking `fetch` rather than hitting a real backend.
- **Browser end-to-end** (`web/tests/*.spec.ts`, Playwright): runs against the actual
  `docker compose` stack on `localhost:8000` (or `BASE_URL`), the same way a judge would
  use it — no mocks, real Postgres, real cookies. `lifecycle.spec.ts` is deliberately the
  rehearsed path a demo video narrates. `phase10.spec.ts` and `recovery.spec.ts` register
  their own accounts and restore any shared state they change, so specs can run in
  parallel and be repeated. The emailed reset flow reads the Mailpit inbox's local API,
  and skips itself when that inbox isn't running.
- **Email in tests.** The backend suite replaces `smtplib.SMTP` with a fake that records
  messages. Its "email off" fixture makes any SMTP connection attempt fail the test, which
  is how the zero-outbound-calls default is asserted rather than assumed.
