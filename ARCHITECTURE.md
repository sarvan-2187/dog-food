# ARCHITECTURE.md — HackFlow

## Shape: a modular monolith, two runtime containers

Everything runs from `docker compose up`, no manual steps, no `.env` to hand-fill (PLAN.md
§1). At runtime there are exactly two containers:

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
├── main.py         # FastAPI app entry: lifespan (create tables + seed), mounts every
│                    #   router, then the SPA static mount + catch-all
├── db.py           # the one engine + get_session() dependency; nothing else builds
│                    #   its own engine
├── seed.py         # idempotent fixture seeding, run automatically on every boot
├── timeutil.py     # utcnow() / ensure_utc() — the only source of "now" in the app
├── auth/           # User model, Role enum, password hashing, session cookies,
│                    #   get_current_user(), require_role() — imported everywhere else
├── events/         # Event model + CRUD
├── teams/          # Team + TeamMembership, invite-link create/redeem
├── submissions/     # Submission model, autosave PATCH, deadline enforcement, gallery
├── judging/         # Rubric + JudgeAssignment models, the assignment algorithm
├── scoring/         # Score model, normalization pipeline, CSV export
├── voting/          # Vote + Comment models, rate limiting, duplicate detection
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
carrying the user id; `get_current_user()` reads and verifies it on every request that
needs identity. There is no JWT, no client-side role claim to trust — every role check
happens against the `role` column read fresh from the database on that request. Passwords
are hashed with `passlib[bcrypt]`; `password_hash` is never part of any response schema.

## Deployment / no-network-calls constraint

`docker compose up` builds both images from local Dockerfiles and pulls only
`postgres:16-alpine` and `node:20-slim`/`python:3.12-slim` from the standard registries at
build time. Once running, the api container makes no *required* outbound network calls —
no cloud database, no auth-as-a-service, no external API, no CDN-fetched font or script in
the served app (PLAN.md §1). This is why fonts fall back to the system stack (see
`DESIGN_SYSTEM.md` §3.1) rather than a Google Fonts `<link>`, and why CSV export uses the
Python stdlib `csv` module instead of a hosted export service. The one exception is
outbound webhooks (below), and those are opt-in per event — an organizer who never
configures one gets the original zero-outbound-calls behavior unchanged.

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

## Outbound webhooks: fire-and-forget, signed, opt-in

An organizer can subscribe an event to a URL (`WebhookSubscription`, DATA-MODEL.md) for
four topics: `submission.submitted`, `assignments.run`, `score.submitted`, and
`event.results_revealed`. `webhooks/service.py`'s `notify()` looks up that event's active
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
  `docker compose` stack on `localhost:8000`, the same way a judge would use it — no
  mocks, real Postgres, real cookies. `lifecycle.spec.ts` is deliberately the rehearsed
  path a demo video narrates.
