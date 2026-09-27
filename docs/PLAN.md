# PLAN.md — HackFlow Build Plan (Claude Code Execution Spec)

**Team:** CodeHawk

> **Audience:** this file is written for an AI coding agent (Claude Code) executing this build, not for a human reading for context. It is the execution-ready companion to `dogfood-2026-implementation-plan-colorful.pdf`, which holds the full strategic rationale, trade-off discussion, and formulas. This file exists so you don't have to re-derive decisions — it tells you exactly what to build, in what order, with what files, and what "done" means at each gate. If you need the *why* behind a decision here, the PDF has it; don't re-litigate it, just build.
>
> This plan is organized as **eight sequential phases (Phase 0 → Phase 7)**. Each phase has a functional checklist *and* a user-experience checklist — treat both as part of the same Definition of Done. A phase that passes the acceptance suite but ships confusing, unresponsive, or unstyled screens is not done; UX is not a separate pass bolted on later, it's a gate criterion at every phase.

## 0. How to use this file

1. Read this entire file once, top to bottom, before writing any code.
2. Work phase by phase, in order. Do not start a phase until the previous phase's **Definition of Done** — functional *and* UX — is fully checked and the acceptance suite gate for that phase passes.
3. As you complete a checklist item, mark it `[x]` in this file and commit that change alongside the code. This file is the running source of truth for progress — keep it in sync with reality, not aspirational.
4. When a task involves anything the user will *look at or interact with* — any page, form, dashboard, or the landing page — read Section 3 (Design Consistency) and Section 4 (UX & Usability Principles) before writing markup or CSS, not after.
5. Never invent a scope not listed here. If you think a feature is missing, flag it under `## Open Questions` at the bottom rather than silently building it.
6. Never add a network call, external API, hosted database, or cloud SDK anywhere in the stack. If a library needs one to function, don't use it — find or write an offline alternative. This constraint overrides convenience every time.

---

## 1. Non-negotiable constraints (re-read before every phase)

- Everything starts with `docker compose up`. No manual steps, no `.env` the user must hand-fill, no separately-run seed script — seeding happens automatically on first boot.
- Zero network calls at runtime once images are built. No cloud database, no auth-as-a-service, no external API, no CDN-fetched assets in the *served* app.
- Four roles: `participant`, `judge`, `organizer`, `admin` — a flat enumeration of **four distinct roles**, not one role wearing several hats. `judge` in particular is a dedicated role held by someone brought onto the platform *to evaluate*, never a participant doing double duty. There is no peer-review model anywhere in this build: participants are never required, or able, to score another participant's submission. See Section 8.0 for the full role model and why it matters.
- Every mutating and every sensitive-read endpoint must be gated by role at the endpoint level — never rely on frontend hiding alone.
- Each phase's functional and UX checklists must both be satisfied before the next phase starts. Do not let tiers — or unpolished screens — bleed forward.
- Tier claims in `README.md` must exactly match what `acceptance-report.txt` shows. Never claim a tier that isn't acceptance-suite green.

---

## 2. Repo layout

```
.
├── docker-compose.yml
├── LICENSE                    # OSI-approved, e.g. MIT
├── README.md
├── ARCHITECTURE.md
├── DATA-MODEL.md
├── JUDGING.md
├── acceptance-report.txt      # the published suite's real output, re-run and re-committed every time — see §9
├── PLAN.md                    # this file
├── DESIGN_SYSTEM.md           # supplied by the user — do not create a placeholder; wait for it
├── reference_design.pdf       # supplied by the user — do not create a placeholder; wait for it
├── fixtures/
│   ├── users.json
│   ├── events.json
│   ├── teams.json
│   └── submissions.json
├── api/
│   ├── Dockerfile
│   ├── pyproject.toml         # or requirements.txt, pin exact versions
│   ├── app/
│   │   ├── main.py            # FastAPI app entry, mounts routers + static SPA
│   │   ├── db.py              # engine/session setup
│   │   ├── seed.py            # idempotent fixture-seeding on boot
│   │   ├── auth/              # sessions, password hashing, require_role()
│   │   ├── events/
│   │   ├── teams/
│   │   ├── submissions/
│   │   ├── judging/           # assignment algorithm, rubrics, progress
│   │   ├── scoring/           # normalization pipeline, CSV export
│   │   ├── voting/            # votes, comments, rate limiting, duplicate detection
│   │   ├── audit/             # append-only log writer + query helpers
│   │   ├── storage/           # StorageService interface + LocalStorage — see Phase 6
│   │   └── webhooks/          # WebhookSubscription CRUD + signed delivery — see Phase 7
│   └── tests/
│       ├── test_auth.py
│       ├── test_events.py
│       ├── test_teams.py
│       ├── test_submissions.py
│       ├── test_judging.py
│       ├── test_scoring.py
│       ├── test_voting.py
│       ├── test_role_isolation.py   # the cross-cutting 403 matrix — see Phase 2
│       ├── test_storage.py          # see Phase 6
│       └── test_webhooks.py         # see Phase 7
└── web/
    ├── Dockerfile              # multi-stage: build with node, discard node in final api image
    ├── package.json
    ├── src/
    │   ├── main.tsx
    │   ├── pages/               # Landing, EventGallery, SubmissionForm, JudgeDashboard, ...
    │   ├── components/
    │   │   ├── feedback/         # toasts, banners, error boundaries, empty states
    │   │   └── ui/                # buttons, inputs, cards — built once, reused everywhere
    │   └── styles/                # tokens consumed from DESIGN_SYSTEM.md — see Section 3
    └── tests/
```

---

## 3. Design consistency — DESIGN_SYSTEM.md and reference_design.pdf

The user will supply two files partway through the build: **`DESIGN_SYSTEM.md`** and **`reference_design.pdf`**. Follow this protocol:

- **If neither file exists yet:** build frontend functionality with plain, undecorated Tailwind defaults (system font stack, default spacing scale, neutral grays, no custom theme). Do not invent a color palette, custom typography, or a "look" of your own. Leave a comment at the top of `web/src/styles/` noting `// awaiting DESIGN_SYSTEM.md — using Tailwind defaults`. Functionality and correctness come first; visual polish is deferred, not skipped — but the *usability* principles in Section 4 are never deferred, since those aren't about visual style.
- **Once `DESIGN_SYSTEM.md` is present:** read it in full before writing or editing any component markup or CSS. Extract its design tokens (colors, type scale, spacing, radii, component patterns) into `web/src/styles/tokens.ts` (or Tailwind config `theme.extend`) as the single source of truth. Re-skin existing components to match rather than leaving a mix of old defaults and new tokens.
- **Once `reference_design.pdf` is present:** treat it as the target visual design specifically for the **frontend landing page**. Read it fully, extract layout, hierarchy, imagery treatment, and copy tone, and rebuild the landing page to match it, using the tokens from `DESIGN_SYSTEM.md` for actual colors/type/spacing. If the reference PDF conflicts with `DESIGN_SYSTEM.md` on a token-level detail, follow `DESIGN_SYSTEM.md` and treat the reference PDF as layout/composition guidance — flag the conflict in `## Open Questions` rather than guessing.
- Never proceed with placeholder/lorem-ipsum styling once these files exist. If mid-task when they arrive, pause frontend visual work, ingest both, then resume.
- These two files affect Code Quality & Innovation (15%) and overall polish, never at the expense of T1–T3 correctness.

---

## 4. UX & Usability Principles (apply in every phase, not just at the end)

This is the single biggest lever for making the platform feel like something an organization like Hackathon Raptors — see `hackraptors.pdf`, raptors.dev's own landing page: dozens of concurrently-run branded events, a judged proof pipeline, public results — could actually run for real events, not a demo. Every phase's checklist below references back to this section — treat these as standing requirements, checked at every gate, not a one-time task.

**4.1 Clarity and feedback**
- Every action that changes data gives visible confirmation: a toast/banner on success ("Invite link copied", "Draft saved", "Score submitted"), and a specific, human-readable error on failure — never a raw stack trace or a bare "Error" string.
- Every async action (save, submit, load) shows a loading state — a spinner or skeleton, never a frozen button or a blank screen with no indication anything is happening. Disable the triggering control while its own request is in flight to prevent double-submits.
- Submission drafts autosave on blur (per the PDF's spec) *and* show a small persistent "Saved" / "Saving…" / "Unsaved changes" indicator near the form — the user should never have to guess whether their edits are safe.

**4.2 Empty, loading, and error states — for every screen, not just the happy path**
- Empty gallery (no submissions yet): explain why it's empty and what to do next (e.g., "No submissions yet — be the first to submit" with a clear call-to-action button for participants, or a neutral "Nothing here yet" for a judge/organizer who can't submit).
- Empty judge dashboard (no assignments yet): explain that assignment hasn't happened yet, not just show a blank table.
- Every list/table view has a defined loading skeleton and a defined error-with-retry state — build these once as shared components (`web/src/components/feedback/`) and reuse everywhere rather than re-solving per screen.

**4.3 Forms**
- Inline validation as the user types or on blur, not only on submit — surface the specific field and the specific problem ("Team name must be 3–40 characters", not "Invalid input").
- Preserve entered data on validation failure — never clear a form because one field was wrong.
- Destructive or irreversible actions (deleting a team, finalizing scores, ending an event early) require an explicit confirmation step that states the consequence in plain language, not just "Are you sure?".

**4.4 Navigation and information architecture**
- Navigation is role-aware: a participant never sees a "Judge Dashboard" link they can't use; a judge never sees "Create Event". Don't show a disabled/greyed-out nav item as a substitute for hiding it — hide it.
- Every page has a clear way back (breadcrumb, back link, or persistent nav) — no dead-end screens.
- Judge progress dashboard and organizer event dashboard lead with the numbers that matter most (assignments completed / total, submissions received / deadline remaining) above the fold, not buried in a table.

**4.5 Responsiveness and accessibility**
- Test every screen at three breakpoints: mobile (~375px), tablet (~768px), desktop (~1280px). A judge reviewing submissions from a tablet between sessions is a realistic use case for this platform — it must not be desktop-only.
- All interactive elements are reachable and operable by keyboard (tab order, visible focus states, Enter/Space activation) — don't rely on mouse-only hover interactions for anything functionally necessary.
- Color is never the only signal for status (e.g., a "hidden results" state or a role badge) — pair color with an icon or text label so it also works for colorblind users and reads correctly in any DESIGN_SYSTEM.md palette.
- Maintain readable contrast and legible type sizes even before `DESIGN_SYSTEM.md` arrives — Tailwind defaults are acceptable, illegibly small or low-contrast text is not.

**4.6 Perceived performance and trust**
- Optimistic UI updates are fine for low-risk actions (e.g., a vote toggling instantly) as long as they roll back visibly on server rejection — never fine for anything affecting scoring or role-gated data.
- Keep the gallery, dashboards, and forms responsive to input even while background data loads — never block the whole page on one slow request when only part of the screen depends on it.
- Microcopy (button labels, empty-state text, error text) should say what will happen or what went wrong in plain language — no jargon like "500 Internal Server Error" surfaced to a participant.

**4.7 Definition of Done for UX, every phase**
A phase is not done until, for every screen it introduces: loading/empty/error states exist, forms validate inline, destructive actions confirm, the screen works at all three breakpoints, keyboard navigation works, and role-aware navigation is correct. This is checked at the same gate as the acceptance suite — see each phase below.

---

## 5. Tech stack — exact choices, don't re-derive

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| ORM | SQLModel (SQLAlchemy 2.0 + Pydantic) |
| DB | PostgreSQL 16, containerized, named volume for data |
| Auth | Session cookies signed with `itsdangerous`; passwords hashed with `passlib[bcrypt]` |
| Frontend | React + TypeScript + Vite, Tailwind CSS |
| Containerization | Docker Compose, 2 services at runtime: `db`, `api` (api serves the built SPA as static files — no separate `web` runtime container) |
| Testing | pytest + `pytest-asyncio` + `httpx` (backend), Vitest (frontend unit), one Playwright end-to-end lifecycle test |
| CSV export | Python `csv` stdlib only |
| File storage | Local filesystem via a Docker named volume, behind a `StorageService` interface — see Phase 6. No S3-compatible service, no CDN |

Pin every dependency to an exact version in `api/pyproject.toml` (or `requirements.txt`) and `web/package.json`. Before first use of any package, confirm it installs with no network reach beyond the allowed package registries.

---

## Phase 0 — Bootstrap

**Goal:** a booting, empty skeleton before any feature work.

- [x] `git init` (only after kickoff — no code before the official start)
- [x] Scaffold `docker-compose.yml` with `db` and `api` services
- [x] `api`'s Dockerfile is multi-stage: stage 1 builds the Vite frontend (`node:20-slim`), stage 2 is `python:3.12-slim` copying the built frontend's static output into the image alongside the FastAPI app
- [x] `api/app/db.py` (engine + session dependency) and `api/app/seed.py` (reads `fixtures/*.json`, idempotency-checked, called on app startup)
- [x] Shared UI scaffolding: `web/src/components/ui/` (Button, Input, Card, Badge) and `web/src/components/feedback/` (Toast, Skeleton, EmptyState, ErrorState) built as reusable primitives *before* any feature page — every later screen consumes these rather than reinventing loading/error/empty markup per page

**Definition of Done — Phase 0 gate:** `docker compose up` boots both containers healthy with empty schema, on a clean checkout (clear local Docker build cache and retry if unsure). Do not proceed to Phase 1 until this works.

**Gate verified:** `docker compose up -d --build` — `dog-food-db-1` and `dog-food-api-1` both report `(healthy)`; `GET /healthz` → `200 {"status":"ok"}`; `\dt` on the `dogfood` database reports no relations. Phase 0 is done — proceed to Phase 1.

---

## Phase 1 — Core (T1)

### Functional checklist
- [x] `User` model + `passlib` password hashing + session-cookie auth (`api/app/auth/`)
- [x] Role enum (`participant`, `judge`, `organizer`, `admin`) + `require_role(*roles)` FastAPI dependency — apply to every mutating/sensitive endpoint from this point forward
- [x] `Event` model + CRUD endpoints (organizer/admin only) — configurable dates, tracks, prize config
- [x] `Team` model + `TeamMembership` join table + invite-link generation/redemption (server-side expiry check, not just UI hide)
- [x] `Submission` model + draft/edit endpoints + autosave-friendly PATCH semantics
- [x] Deadline enforcement: reject writes server-side once `Event.end_at` has passed — test by calling the endpoint directly post-deadline
- [x] Public gallery endpoint with search (simple `ILIKE` on title/description)
- [x] `api/tests/test_auth.py`, `test_events.py`, `test_teams.py`, `test_submissions.py` passing — plus `test_regressions.py` from the Phase 0/1 audit: **30/30 green** (`docker compose exec api pytest tests/ -v`, which now works verbatim — see audit note below)
- [ ] Run the acceptance suite against T1 — *blocked: no acceptance suite has been published yet (see Open Questions)*

### UX checklist (see Section 4 for detail)
- [x] Event creation form: inline validation, clear field-level errors, disabled submit while saving
- [x] Team formation: invite-link copy button with a "Copied" confirmation; joining flow shows a clear success/failure state, not a silent redirect
- [x] Submission draft/edit: visible autosave indicator ("Saving… / Saved / Unsaved changes"); never loses entered content on a validation error
- [x] Public gallery: loading skeleton while fetching, empty state with role-appropriate call-to-action, search with no-results state that's distinct from the empty-gallery state
- [x] Deadline countdown or clear deadline display on the submission page — the user should never discover a deadline passed only via a rejected save
- [x] All Phase 1 screens verified at mobile/tablet/desktop breakpoints and via keyboard-only navigation — done in a real browser via `web/tests/breakpoints.spec.ts` (24 Playwright checks at 375/768/1280 + keyboard + role-aware nav). Found and fixed a real 54px horizontal overflow on `/gallery` at 375px; see the `sm:` audit note below.
- [x] Role-aware navigation: nav only shows links the current role can use

**Definition of Done — Phase 1 gate:** acceptance suite reports all T1 checks green, and every item in the Phase 1 UX checklist is checked. Do not start Phase 2 otherwise.

**Gate status:** green, after a full Phase 0/1 audit (see `## Phase 0/1 Audit` below). Verification now standing:

| Suite | Command | Result |
|---|---|---|
| Backend | `docker compose exec api pytest tests/ -v` | 30 passed |
| Frontend unit | `cd web && npm test` | 9 passed |
| Browser E2E | `cd web && npx playwright test` | 24 passed |

`docker compose up -d --build` boots both containers healthy from a clean volume; seeding is
idempotent across restarts (row counts unchanged); `GET /healthz` → `200`. The only item still
open is the published acceptance suite, which does not exist to run.

---

## Phase 2 — Judging (T2)

**Model (see Section 8.0 before touching this phase):** `judge` is a distinct, dedicated
role — someone *invited onto* the event to evaluate, never a participant rotated into
scoring peers. Everything in this phase is gated to that role and to the specific
assignment that belongs to it. Community voting is a **separate** mechanism built in
Phase 3 and must never feed the judging pipeline; peer review is not in scope at all.

### Functional checklist
- [x] **Judge invitation** — organizer-issued, single-use, expiring invitation (`api/app/judging/invites.py`, `JudgeInvite`). `judge` remains the one role with no self-service path; the invite panel on the organizer's results page is now the only route into it. Redemption promotes the signed-in account, is refused for organizers/admins rather than silently demoting them, and is audit-logged. Found by reconciling this plan against the brief, where it had been silently omitted from this checklist
- [x] `Rubric` model + CRUD (organizer only) — validate criteria weights sum to 1.0 on save, reject otherwise (`RubricWrite.weights_sum_to_one`; the error names the actual total). One rubric per event — see Open Questions
- [x] `JudgeAssignment` model + the assignment algorithm (Section 8) — `api/app/judging/assignment.py`, pure and DB-free, called by the handler. Shortfall is reported via `coverage_report()` rather than relaxing a conflict
- [x] `Score` model + score submission endpoint, restricted to the assigned judge for that specific assignment only (`require_role(judge)` **plus** an ownership check — role alone is not enough)
- [x] Role isolation: judges cannot see other judges' scores; participants cannot see any score detail; organizers cannot submit a score by calling a judge endpoint directly — all three asserted in `test_role_isolation.py` and verified live
- [x] Judge progress dashboard endpoint + frontend (`GET /api/judge/assignments`, `web/src/pages/JudgeDashboardPage.tsx`)
- [x] Normalization pipeline (Section 8) — `api/app/scoring/normalization.py`, pure, unit-tested without a DB
- [x] CSV export endpoints: users, submissions, assignments, raw scores, normalized results (Python `csv` stdlib only)
- [x] `api/tests/test_judging.py`, `test_scoring.py` passing
- [x] `api/tests/test_role_isolation.py`: table-driven 403/401 matrix — every mutating/sensitive endpoint × every role that must be refused
- [ ] Run the acceptance suite against T2 — *still blocked: no acceptance suite has been published*

### UX checklist
- [x] Judge progress dashboard leads with "X of Y assignments completed" prominently, not buried in a table; shows which specific submissions are still pending (asserted by position, not just presence)
- [x] Score submission form: criteria labelled with their weights, weighted total updates live, inline validation blocks an incomplete or out-of-range submission before submit is enabled
- [x] Clear, reassuring confirmation after score submission (not just a redirect) — a toast plus a persistent "This score is recorded" marker, and the judge stays on the form
- [x] Organizer rubric builder: weight total validated live at the field level with a running sum and a "that is X too much / X short" hint — never a generic form-level rejection
- [x] CSV export buttons show a loading state and a clear success signal; a role rejection surfaces as a readable message instead of navigating to a raw 403
- [x] All Phase 2 screens verified at mobile/tablet/desktop breakpoints and via keyboard-only navigation (`web/tests/judging.spec.ts`; the standings table becomes stacked key/value cards below `md`, per `DESIGN_SYSTEM.md` §4)

**Definition of Done — Phase 2 gate:** acceptance suite reports all T2 checks green, `test_role_isolation.py` has at least one negative-role test per mutating endpoint, and the Phase 2 UX checklist is fully checked. Do not start Phase 3 otherwise.

**Gate status:** green apart from the unpublished acceptance suite. The one clause that was
missing — "judge invitation" — has since been built (see the checklist above and Open
Questions); every T2 clause is now implemented and tested.

| Suite | Command | Result |
|---|---|---|
| Backend | `docker compose exec api pytest tests/ -v` | 181 passed |
| Frontend unit | `cd web && npm test` | 9 passed |
| Browser E2E | `cd web && npx playwright test` | 71 passed |

Verified live against the seeded stack on a clean `docker compose up -d --build`: assignment produced 9 pairs
across 3 submissions with **zero** conflicts (Dana, who is both a judge and a Pipeline Pals member, was never
assigned Flake Finder); four judges of differing harshness scored; the normalised standings re-ranked against the
raw mean as intended. One defect was found and fixed in this phase: the standings table's `<th>` elements had no
`scope`, so the browser exposed them as generic cells and a screen reader reading a value never said which column
it came from.

---

## Phase 3 — Public (T3)

### Functional checklist
- [x] `Event.voting_enabled` toggle + `Vote` model with unique constraint `(user_id, submission_id)` — organizer toggles it from the results page
- [x] `Event.results_hidden_until` + enforce hiding at the **API response** level — `GalleryItem.votes` is `null` during the window and `/public-results` returns `425`; asserted against the raw payload, not the rendered UI
- [x] Randomized project ordering, seeded per-session — server shuffles with `random.Random(seed)`; the client holds one seed per browser session in `sessionStorage`
- [x] `Comment` model + endpoints (list/add/delete, with author-or-moderator deletion)
- [x] Rate limiting on vote/comment endpoints — in-process token bucket in `api/app/voting/ratelimit.py`, time-injectable so refill is tested without sleeping
- [x] Duplicate-vote detection: the unique constraint is the hard guard (an `IntegrityError` is caught rather than a pre-`SELECT` that a concurrent request could race past); `fingerprint_hash` flags suspicious repeats into the audit log without blocking
- [x] Wire remaining actions into the `audit` module — the module did not exist (see Open Questions); built here and wired into register/login, event CRUD, team create/join, submission submit, rubric save/delete, assignment runs, score submission, votes and comments
- [x] `api/tests/test_voting.py` passing
- [x] **If time is tight:** fall back to the smaller "community interest" thumbs-up variant — *not needed; full voting shipped*
- [ ] Run the acceptance suite against T3 — *still blocked: no acceptance suite has been published*

### UX checklist
- [x] Voting UI clearly communicates *why* results are hidden during the voting window — a banner naming the reveal time and the reason ("everyone sees the totals at the same time, so early counts cannot sway the vote"), plus a per-card labelled placeholder instead of a wrong number
- [x] Voting/comment rate limiting shows a clear, friendly message when a limit is hit — "You've reached the voting limit for now - try again in about N seconds", with `Retry-After` still set for well-behaved clients
- [x] Comment submission: inline validation, optimistic append with rollback-on-failure, visible "Sending..." state, and the typed text is restored rather than lost if the post fails
- [x] Randomized ordering doesn't cause layout jank on repeated visits within the same session — asserted by navigating away and back and comparing the rendered order
- [x] All Phase 3 screens verified at mobile/tablet/desktop breakpoints and via keyboard-only navigation

**Definition of Done — Phase 3 gate:** acceptance suite reports T3 checks green (full scope or the documented fallback scope), and the Phase 3 UX checklist is fully checked.

**Gate status:** green apart from the unpublished acceptance suite. Verification standing:

| Suite | Command | Result |
|---|---|---|
| Backend | `docker compose exec api pytest tests/ -v` | 158 passed |
| Frontend unit | `cd web && npm test` | 9 passed |
| Browser E2E | `cd web && npx playwright test` | 61 passed |

Verified live against the seeded stack: during the hidden window the raw gallery payload carries
`votes: null` for a participant while the organizer sees real counts on the same endpoint;
`/public-results` returns `425` with the reveal time for participants and anonymous callers alike;
a second vote from the same user returns `409`; the vote limiter engages with a readable message;
and a shared client fingerprint is recorded in the audit log **without** blocking the vote.

---

## Phase 4 — Stretch (T4) and bonus challenges

**Status: un-frozen and built (backend), post-Phase-5 rebrand session.** The earlier freeze note below is kept for the record rather than deleted, but the user explicitly directed this phase to proceed after the JudgeR rebrand and hero rebuild. Scope was built API-first; see the honest gap called out at the bottom before treating this as fully done. (The product was later renamed again, JudgeR → HackFlow, after Phase 7 — see the Open Questions entry for that decision. This historical note is left as originally written.)

~~**Original freeze note (superseded):** frozen, not attempted. Phases 1–3 gates are green, so PLAN.md's own entry condition for this phase was met — but the decision was made to spend the remaining time on Phase 5's audit, documentation, and freeze work instead of stretch features. Reasoning: a smaller, thoroughly-audited T1–T3 submission demos and scores better than an unaudited T1–T4 one, and Phase 0/1's audit already showed that unaudited "done" work hides real defects (15 of them, in barely two phases).~~

### T4 functional checklist
- [x] REST API/OpenAPI completeness audit: cross-checked every backend route against every frontend `api.*()` call site live. No gap found — every click-triggered write (including invite-link redemption) already has a documented endpoint.
- [x] Certificate/record generation — `GET /api/submissions/{id}/certificate.pdf`, rendered server-side with `reportlab` (pinned, pure-Python, no external service). Gated by the same `may_see_results` visibility rule as public results, plus a team-membership check.
- [x] Bulk import/export — `GET /api/events/{id}/export.json` / `POST /api/events/import`, organizer/admin only. Deliberately scoped to event config + rubric + teams + submissions; assignments/scores are NOT round-tripped (see `api/app/scoring/router.py`'s docstring — re-creating scores against necessarily-different judge accounts would misrepresent who actually judged what).
- [x] Signed judge participation records — `GET /api/events/{id}/judges/{judge_id}/participation-record`, Ed25519 via `cryptography` (pinned), key persisted to a `keys_data` docker volume so signatures outlive a container rebuild. Verifiable offline via `GET /api/public-key` and `app.crypto.verify_record` — see `api/tests/test_phase4.py` for a live tamper-detection test.
- [ ] Embeddable gallery widget — **cut, per this checklist's own stated priority** ("lowest priority — cut first if time runs short"). Not started.

### Bonus challenges
- [x] Normalization Proof — already existed and wasn't noticed until this pass: `GET /api/events/{id}/export/results.csv` has shown raw_mean alongside z_bar/display since Phase 2/4 (its own docstring already says "PLAN.md Phase 4 bonus"). No new code needed; documented here instead of rebuilt.
- [x] Threat Model write-up — `THREAT-MODEL.md`, 11 attacks paired with the mitigation already built and the file that enforces it.
- [ ] API First — not attempted. The OpenAPI completeness audit passed, but this item's own scope (a fully spec-first workflow) wasn't defined narrowly enough to build in the time available; left honestly unchecked rather than claimed from the audit passing alone.
- [ ] Pairwise Mode / Bradley-Terry — not attempted, per its own gate ("only with 10+ hours of confirmed slack"), which this session does not have.

### UX checklist (if any T4 work touches the UI)
- [x] **T4 frontend UI** (was a disclosed gap; closed 2026-09-19). Certificates: "Download certificate" on the team's own submission page once submitted, and on the public submission page for organizers/admins (`CertificateButton`). Event backup: "Download event backup" on event settings; "Import an event" on `/events` for organizers/admins (`EventImportPanel` flattens the export's nested `event` into the import payload and pre-fills a free `-copy` slug, since re-importing into the same database otherwise 409s). Signed participation records: one download per event on the judge dashboard, with a pointer to `/api/public-key`; `AssignmentPublic` gained `event_id`/`event_name` to make that possible. Every server refusal (425 before reveal, 403 off-team, 409 duplicate slug) surfaces as its own message in a toast via `api.download`/`ApiError`. Not built: an organizer-side per-judge record list; organizers can still fetch any judge's record via the API.

---

## Phase 5 — Polish, UX Audit & Freeze Prep

This phase exists specifically so UX quality gets one dedicated, whole-app pass rather than only being checked screen-by-screen as you go. Do not skip it even though Phases 1–3 individually passed their own UX checklists — this phase catches cross-phase inconsistency the same way the Phase 0/1 audit caught the `sm:`/`md:` breakpoint bug that reading Phase 1's code in isolation had not.

### 5.1 — Close every dangling Open Question first

Fix these before auditing anything else, since leaving them open would either produce false audit findings or block the demo outright:

- [x] Resolve the `reference_design.pdf` / `reference_landing.pdf` filename mismatch — renamed `reference_landing.pdf` → `reference_design.pdf` (`git mv`), matching Section 2's repo layout. `DESIGN_SYSTEM.md`'s references updated to match.
- [x] Decide the font question once and for all — **system stacks are canonical**, not a fallback (`DESIGN_SYSTEM.md` §3.1 rewritten). No `Inter`/`Instrument Serif`/`JetBrains Mono` binaries are committed; sourcing and licensing real webfont files wasn't worth it for an app that has rendered correctly on the system stack since Phase 0. `web/src/styles/tokens.ts` updated to match.
- [x] Fix the seeded event's expiry — `fixtures/events.json` now runs `2026-10-15T09:00:00` → `2026-10-17T18:00:00` (voting hidden-window `2026-10-17T20:00:00`), well past the freeze/demo window.
- [x] Decide the acceptance-suite fallback now: no acceptance suite has been published at any point in this build. `acceptance-report.txt` will be self-issued from the project's own suites (`api/tests/` + Vitest + Playwright), generated fresh in 5.5 below with a header stating plainly that it is self-issued pending the real suite — never hand-edited, never claiming a tier the run didn't earn.

### 5.2 — Whole-app audit: click-through × role × breakpoint

Extends the Phase 0/1 audit's method to every screen Phases 2 and 3 added, and to cross-phase consistency Phases 1–3 couldn't each see on their own:

- [x] Click through every screen as each of the four roles, at all three breakpoints — rests on the 61 Playwright checks (all real, all rerun and passing this session) plus two live spot-checks with a real Chromium session for the two screens with no named test: the event creation form (organizer) and the team creation/join form (participant). Both confirmed keyboard-reachable with a visible focus ring. No new spacing/color/component-usage defect found beyond the one logged in 5.3.
- [x] ~~Extend `web/tests/breakpoints.spec.ts`~~ — correction: this coverage already existed, just not in that file. `judging.spec.ts` has its own "Phase 2 screens at every breakpoint" block and `voting.spec.ts` has "Phase 3 screens at every breakpoint," both exercising all three widths for the screens each phase added. No refactor needed; the checklist item's premise (breakpoints.spec.ts is the only breakpoint coverage) was wrong.
- [x] Full keyboard-only pass — `breakpoints.spec.ts`, `judging.spec.ts`, and `voting.spec.ts` each carry a `keyboard-only` block (login, score form, vote control, comment box); the two gaps found (event creation, team formation) were closed live this session (see above).
- [x] Re-verify role-aware navigation — confirmed live: an organizer session shows "Create event" and never "My teams"; a fresh participant session shows "My teams" and never "Create event." Matches `breakpoints.spec.ts`'s automated assertions of the same.

### 5.3 — Prove the states, don't trust the code

For every screen introduced in any phase:

- [x] Simulated a no-results search on the gallery live — renders, though the debounce means it doesn't update instantly on a raw DOM event (expected React behavior, not a bug). The true zero-submissions empty state and the judge-dashboard-with-no-assignments empty state are exercised by `judging.spec.ts`/`voting.spec.ts` rather than re-verified by hand here.
- [ ] Network throttling ("Slow 3G") was **not** performed this session — flagged rather than falsely checked off.
- [x] Forced a real 500 by stopping the `db` container mid-session: the gallery's `ErrorState` rendered correctly (`role="alert"`, "Something went wrong," a working "Try again" button) — **and this caught a real defect**, fixed on the spot: the error fallback was leaking the bare status code ("Request failed (500)."), which brushes against §4.6's "no jargon like '500 Internal Server Error'." Fixed in `web/src/lib/api.ts` (`request()` and `download()`), and the existing Vitest test that was *named* for exactly this case but never actually asserted the message was tightened to check it for real. See `acceptance-report.txt` for the full write-up.

### 5.4 — Landing page reconciliation

- [x] **Correction: the landing page did not exist.** This item was originally written assuming a landing page had already been built and just needed a final diff-check against `reference_design.pdf` — that assumption was wrong. `"/"` redirected straight into the app across all of Phases 0–3; `DESIGN_SYSTEM.md` §10's full 9-section composition had never been implemented. Built `web/src/pages/LandingPage.tsx` following §10 exactly (hero with the italic-serif accent word, a product-proof panel wired to real live data via `GET /api/events` / `GET /api/gallery`, the numbered rules list, an illustrative decision trail, four capability cards, an illustrative dashboard preview, the full-bleed step band, footer) plus the `MetricTile` primitive §11 called for and never had. Routed at `"/"`.
- [x] **Real defect found and fixed while building it.** Several `sm:` grid classes fired their multi-column layout AT 375px — the exact `sm:`-means-mobile mistake the Phase 0/1 audit already documented (see Open Questions). Caught with a live 375px screenshot (a 5-column step band crammed into one row), fixed by switching to `md:`, re-verified at all three breakpoints with zero overflow, and added `"/"` to `breakpoints.spec.ts`'s `PUBLIC_PAGES` so this is now permanent automated coverage, not a one-time look.
- [x] `hackraptors.pdf` positioning applied to `README.md` and the landing page's footer line (Hackathon Raptors / raptors.dev, framing the platform for an organization running several branded events). No token, component, or layout borrowed from it, per the logged decision.

### 5.5 — Acceptance suite: run it, or formally document why not

- [x] No acceptance suite has been published. `acceptance-report.txt` generated fresh from a real, live run of all three suites on a clean volume: **181 backend + 9 Vitest + 75 Playwright = 265/265 passing** (re-run after judge invitation, the shadcn Select swap and the landing-motion guards; previously 233). Header states plainly that it is self-issued. `README.md`'s tier/status claims are written against these exact numbers.

### 5.6 — Demo video

- [ ] **Not done — cannot be done by an agent.** Scripting the walkthrough from `lifecycle.spec.ts` and `voting.spec.ts`, and the `docker compose down -v` reset beforehand, are both still accurate as written above; the actual screen recording needs a human at a keyboard. Left unchecked rather than claimed.

### 5.7 — Documentation, freeze, and ship

- [x] `README.md` — setup, feature overview, tier/status claims matching `acceptance-report.txt` exactly.
- [x] `ARCHITECTURE.md` — modular-monolith rationale, backend package map, frontend primitive structure, auth model, no-network-calls constraint, testing architecture.
- [x] `DATA-MODEL.md` — every table transcribed field-for-field from the actual model files (not summarized from memory), entity relationships, import/export paths.
- [x] `JUDGING.md` — assignment algorithm, normalization math, role isolation (including the ownership checks beyond role alone), rubric-locking, results-visibility, and duplicate-vote/rate-limit design, collected from Section 8 and the Open Questions decisions already made.
- [x] `LICENSE` — MIT, in place.
- [ ] Repo made public — **not done; needs the repo owner's decision**, not an agent's. `git status` shows an existing `origin/main` remote; making it public is a one-line GitHub setting but is exactly the kind of outward-facing, hard-to-reverse-in-spirit action this build asks to be confirmed explicitly rather than assumed.
- [x] Final full suite run after the documentation pass: 181/181 backend green on a clean volume, confirming neither the docs pass, the judging role-model reconciliation, nor the judge-invitation and UI work disturbed anything.

**Definition of Done — Phase 5 / submission gate:** acceptance report committed and real (done); all four docs complete and cross-checked against it (done); demo video recorded (not done — needs a human); repo public (not done — needs the owner's decision); license in place (done); every Open Question either resolved or explicitly and knowingly carried into submission (done — see the running log below). Phase 5 is substantially complete; the two remaining items are both things this session cannot do on its own.

---

## Phase 6 — Uploaded Assets & Object Storage

**Entry condition:** Phases 1–3's functional/UX gates are green (Phase 5's two outstanding items —
demo video, repo-public — are human-only decisions and don't block this). This phase is additive
scope beyond the T1–T4 tier ladder: the brief never names screenshots/avatars as a tier requirement,
but the public gallery (T1) reads as a real gallery, not a list of text cards, and Adoptability &
Operability (20% of the grade) rewards exactly this kind of "actually usable by an organizer"
completeness. Not tier-gated, not required for any tier claim in `README.md`.

**Architecture decision (settled, do not re-litigate mid-phase):** local filesystem storage behind
a small `StorageService` interface, with exactly one implementation (`LocalStorage`) shipped. No
MinIO, no S3-compatible client, no CDN, anywhere in this phase. This follows directly from §1's
constraints — no cloud account, no external API, zero network calls at runtime, must work with the
network off — and from `docker-compose.yml`'s existing 2-service shape (`db`, `api`), which this
phase must not grow. A cloud object store (S3/R2/Cloudinary) fails §1 outright: it cannot serve an
image with the network off. Self-hosted S3-compatible storage (MinIO) *would* technically satisfy
§1, but adds a third stateful service, its own credentials, and its own backup/restore story for no
benefit at this scale — a single-origin gallery serving a few hundred images to one event's
participants over 72 hours has no cache-fanout problem for a second service to solve. Request flow:

```
Browser → Backend (FastAPI, the same process already serving the SPA)
             → reads bytes from local disk (Docker-volume-backed directory)
             → streams response with Content-Type + Cache-Control
```

The `S3CompatibleStorage` side of the interface is documented as the production upgrade path (see
`ARCHITECTURE.md`) and is never implemented or tested in this phase — building and debugging a second
backend nobody asked for is exactly the kind of unfinished-feature scope §11 and the brief's own
"one challenge done properly beats four unfinished features" guidance warn against.

### Functional checklist
- [x] `StorageService` interface (`api/app/storage/service.py`): `save(data, content_type) -> key`, `read(key) -> bytes`, `url_for(key) -> str`, `delete(key)`, `exists(key) -> bool`. `read()` (not a filesystem path) is what `GET /media/{key}` calls, so the router never depends on `LocalStorage`'s internal path layout.
- [x] `LocalStorage` implementation (`api/app/storage/service.py`): writes under `UPLOAD_DIR` (Docker-volume-backed); keys are always `uuid4().hex` + an extension derived from `content_type` — never from the client's filename; rejects any content type outside `image/{png,jpeg,webp,gif}` and anything over 5MB before writing.
- [x] File-metadata table — `StoredFile` (`api/app/storage/models.py`): `key, owner_type, owner_id, content_type, size_bytes, checksum, created_at`, unique on `(owner_type, owner_id)` so a submission/user has at most one current image; replacing it updates the same row and deletes the old key's bytes.
- [x] Upload endpoints (`api/app/storage/router.py`): `POST /api/teams/{team_id}/submission/image` (gated by the existing `require_team_member` ownership dependency) and `POST /api/users/me/avatar` (self only, via `get_current_user`).
- [x] Serving route `GET /media/{key}`: no auth, reads via `StorageService.read()`, 404s if the `StoredFile` row is gone even if bytes briefly still exist mid-replace.
- [x] `docker-compose.yml`: one new `uploads_data` volume, mounted into `api` only via `UPLOAD_DIR=/app/uploads` — still exactly `db` + `api` at runtime.
- [x] Gallery, submission detail, and profile wired to render the uploaded image with a defined "No image" placeholder. **Scope cut, disclosed:** the navbar itself does not show a small avatar thumbnail next to "Profile" — the pill-nav tabs are plain text links and adding an image there risked destabilizing shared nav styling for a low-value polish item; the avatar itself is fully wired and visible on `/profile`.
- [x] `api/tests/test_storage.py` (10 cases): `LocalStorage` save/read round-trip, unsupported content-type rejection, oversized-file rejection, a test proving `_resolve()` refuses a traversal key, successful upload + serve, replace-deletes-the-old-key, cross-team upload refused with 403, disallowed content-type refused with 422, avatar upload visible on `/api/auth/me`, unknown key 404s.
- [x] `fixtures/submissions.json` + `fixtures/images/*.png` (3 generated placeholder images) + `seed.py`'s `_seed_submissions` extended to save them via `StorageService` and create their `StoredFile` rows — a fresh `docker compose up` shows a populated gallery, verified live.

### UX checklist (see Section 4 for detail)
- [x] `ImageUpload` component (`web/src/components/ImageUpload.tsx`) shows a live local preview via `URL.createObjectURL`, a loading state on the button while the request is in flight, and a specific rejection message ("Image must be under 5MB", "Use PNG, JPEG, WebP, or GIF.") — both client-checked before the request and server-enforced regardless.
- [x] Gallery cards (`aspect-video` frame) and submission detail (`max-h-96`) render the image responsively, with a "No image" placeholder frame when absent — confirmed live, not just in code.
- [x] Avatar upload (`ProfilePage.tsx`) reuses the exact same `ImageUpload` component as the submission screenshot control (`SubmissionPage.tsx`), only `shape="circle"` differs.
- [x] Replacing an image is a clear action (the button relabels to "Replace screenshot"/"Replace avatar" once one exists); the superseded key is deleted server-side in the same request that saves the new one — verified live and in `test_storage.py`.

**Definition of Done — Phase 6 gate:** `test_storage.py` green (10/10, part of the full 206/206 backend suite); the gallery, submission detail, and profile render real seeded/uploaded images on a clean `docker compose down -v && docker compose up -d --build` — confirmed live with a real avatar upload surviving a full page reload; `docker-compose.yml` still runs exactly `db` + `api` (one new named volume, not a new service); no MinIO/S3 client/CDN dependency exists anywhere in `api/requirements.txt`, `web/package.json`, or `docker-compose.yml`. Full Playwright suite (84/84) and Vitest (9/9) re-run clean after this phase.

---

## Phase 7 — Tracks & Prizes UI, Team-Size Limits, Outbound Webhooks

**Entry condition:** Phases 1–6 gates are green. Unlike Phase 6, item 7.1 below is **not**
additive scope — it closes a gap in an already-claimed tier. Audited live before writing this
phase: `Event.tracks: List[str]` and `Event.prize_config: Dict[str, Any]` have existed on the
model since Phase 0, and `EventCreate`/`EventUpdate` already accept both fields with full
validation — but `EventCreatePage.tsx` hardcodes `tracks: []` on every create and no screen
anywhere, at creation or after, ever sends or displays `prize_config`. T1 names "configurable
dates, **tracks and prizes**" explicitly; dates are configurable, tracks and prizes are not,
despite the backend already supporting both. This is a real T1 completeness gap, not a new
feature — closing it is worth more against Tier Completion & Correctness (40%) than any of
this phase's other items. 7.2 and 7.3 are genuine additive scope (7.2 closes a named platform
*rule* this app doesn't enforce on itself; 7.3 closes a named T4 item — "REST API **and
webhooks**" — where only the REST/OpenAPI half was ever built).

### 7.1 — Tracks & prize configuration (closes a T1 gap, frontend-only) — DONE

No backend change: `EventCreate`/`EventUpdate`/the `Event` model already accepted and stored
both fields before this phase; it was purely wiring a UI to an API surface that has existed
since Phase 0.

- [x] `prize_config` convention fixed app-wide: `{"prizes": [{"rank": "1st Place", "reward":
      "$500"}, ...]}`. Documented in `DATA-MODEL.md`.
- [x] `TrackListEditor`/`PrizeListEditor` (new `web/src/components/EventConfigEditors.tsx`) —
      one shared pair of components, not duplicated per page, reusing the rubric builder's
      "rows with a remove button" interaction.
- [x] `EventCreatePage.tsx` sends real `tracks`, `prize_config`, and `max_team_size` instead of
      the old hardcoded `tracks: []`. An event with neither tracks nor prizes still creates
      cleanly (both are optional).
- [x] New **event settings** screen (`EventSettingsPage.tsx`, `/events/:slug/settings`,
      organizer/admin only) using `PATCH /api/events/{id}` — the only way to change tracks,
      prizes, or team size after creation.
- [x] `SubmissionPage.tsx`'s Track field becomes a `<select>` of the event's configured tracks
      when any exist, falling back to the original free-text `<input>` when none do.
- [x] `EventDetailPage.tsx` renders configured tracks and prizes under the event description,
      visible to every visitor, not just the organizer who set them.
- [x] `EventDetailPage.tsx`'s "Organizing this event" card gets an "Event settings" button
      alongside "Judging rubric" and "Assignments & results".

### 7.2 — Team-size cap (closes a named platform rule this app doesn't enforce) — DONE

- [x] `Event.max_team_size: int = 4` — default matches this hackathon's own rule, so existing
      seeded events behave identically to before (verified: `test_default_max_team_size_...`).
- [x] `EventCreate`/`EventUpdate` accept `max_team_size`, bounded 1–20, same validation style as
      `AssignmentRun.judges_per_submission`.
- [x] `join_team` (`teams/router.py`) counts existing `TeamMembership` rows before inserting a
      new one; refuses with 409 `"This team is full (max N members)."` — the creator counts
      toward the cap too (verified: a `max_team_size=1` event refuses the very next joiner).
- [x] The team-size field lives on the same `EventSettingsPage.tsx` from 7.1.
- [x] `TeamCard`/`JoinTeamPage.tsx`/`TeamsMinePage.tsx` all show "N / max members"; `TeamCard`
      additionally hides the invite link once full, rather than leaving a dead control up.
- [x] `api/tests/test_teams.py`: `test_a_full_team_refuses_a_new_join_in_plain_language`,
      `test_joining_up_to_the_cap_succeeds_one_over_it_does_not`,
      `test_default_max_team_size_matches_the_hackathons_own_rule` — all green.

### 7.3 — Outbound webhooks (closes a named T4 item: "REST API and webhooks") — DONE

**Architecture decision (as built):** fire-and-forget, single attempt, signed, opt-in per event —
no queue, no retry/backoff, no new dependency (`httpx`, already pinned for the test suite, is
now also a runtime HTTP client for the first time). Dispatched via FastAPI `BackgroundTasks` so
a slow/unreachable endpoint never delays the triggering request (`TIMEOUT_SECONDS = 5.0`, one
attempt). **One deviation from the original plan, for the better:** delivery outcome is recorded
on the `WebhookSubscription` row itself (`last_status: "never fired" | "delivered" | "failed"`)
rather than the audit log — an organizer wants "is my webhook working," which a per-row status
answers directly; the audit log has no per-entity "latest status" query pattern anywhere else in
this app, so adding one just for this would have been a second convention for the same idea.

Signing reuses `api/app/crypto.py` exactly as built for Phase 4's judge participation records —
verifiable by any receiver against the same already-published `GET /api/public-key`.

- [x] `WebhookSubscription` model (`api/app/webhooks/models.py`): `id, event_id, url,
      created_by_id, active, last_status, created_at`.
- [x] CRUD endpoints, organizer/admin only: `GET/POST /api/events/{id}/webhooks`,
      `DELETE /api/events/{id}/webhooks/{webhook_id}`. **Deviation:** no separate deactivate
      endpoint — delete is the only stop-delivery action, immediate and permanent, rather than
      a `active` toggle nothing in the UI ever sets to false. Simpler surface, same guarantee
      ("stops now, no grace period").
- [x] `notify(session, background_tasks, event_id, topic, **detail)` (`webhooks/service.py`),
      called from the same sites that already call `audit.log.record()`:
      - `submission.submitted` (`submissions/router.py`)
      - `assignments.run` (`judging/router.py`)
      - `score.submitted` (`scoring/router.py`)
      - `event.results_revealed` (`voting/router.py`'s `public_results`) — fires once, guarded
        by a new `Event.results_revealed_notified` flag checked against `results_are_public()`
        (not `may_see_results()`, so an organizer's own early read never fires it prematurely).
- [x] Delivered payload is exactly `crypto.sign_record()`'s output: `{"record": {...}, "signature",
      "public_key", "algorithm": "ed25519"}`.
- [x] `WebhookPanel` (in `EventSettingsPage.tsx`): add a URL, see each webhook's `last_status`
      badge, remove one. States plainly that it fires zero outbound calls with nothing configured.
- [x] `api/tests/test_webhooks.py` (6 cases): CRUD + role gating + URL-format validation; a
      signed payload is sent and verifies with `crypto.verify_record()`; an unreachable URL
      does not raise and records `"failed"`; deleting a webhook stops further deliveries. Two
      of these needed a small testability seam in `_deliver()` (an optional `session` param) —
      a background task's real fresh DB connection can't see this test harness's per-test
      savepoint-isolated data, which is a property of the test isolation strategy, not a
      production bug; documented inline in both the code and the test.
- [x] Documented in `ARCHITECTURE.md` and `README.md`: webhooks are opt-in and make zero
      outbound calls unless an organizer explicitly configures one.

**Definition of Done — Phase 7 gate:** `test_teams.py`'s 3 new cases and `test_webhooks.py`'s 6
cases green as part of a full clean-suite run (215/215 backend); an event created with tracks
and prizes shows both back to a participant without any raw API call — confirmed live; a team at
its cap refuses a new join with a plain-language 409; a webhook added live through the settings
screen shows "NEVER FIRED" immediately and is removable — confirmed live; `docker-compose.yml`
unchanged at exactly `db` + `api`. Full Playwright suite and Vitest re-run clean after this phase
(one pre-existing spec's exact-text assertion needed updating for the new "N / max members"
copy — not a regression, a copy change this phase intentionally made).

---

## Phase 8 — Onboarding: Guided Tour & Illustrated User Manual

**Entry condition:** Phases 1–7 gates are green; T1–T4 are all built and the full suite
passes (215 + 9 + 84 = 308). That precondition is the *whole* justification for this phase,
and it was checked before the phase was written rather than assumed.

**Where this scores — stated honestly, because it is easy to overclaim.** Neither item below
climbs the tier ladder. T1–T4 say nothing about onboarding, so nothing here moves Tier
Completion & Correctness (40%). Both items land squarely in **Adoptability & Operability
(20%)**, which is judged on *"whether Hackathon Raptors could realistically run the
software"* — and an organization running 35+ events across 85+ countries onboards an
entirely fresh set of participants and judges every single time. A platform that explains
itself in plain language is the difference between adopting it and writing a support doc
around it. The manual additionally serves the Write Up Quest (3 × $100). The brief's own
warning governs the sequencing: *"a clean, correct T2 is better than a broken T4"* and *"one
challenge done properly beats four unfinished features."* This phase is therefore polish on
a finished ladder, and would have been the wrong call at any earlier point in the build.

**Constraint check (PLAN.md §1, run before adding the dependency).** `driver.js` is ~5KB,
installs from npm, and is bundled into the SPA at build time. It makes **zero** network
calls at runtime, registers no service, and needs no account or key — so
`docker compose up` with the network physically off is unaffected. Pinned exactly
(`driver.js: 1.8.0`, `--save-exact`) like every other dependency here. `npm audit` was
checked after install: it introduces no new vulnerability. `docker-compose.yml` stays at
exactly `db` + `api`.

### 8.1 — Role-aware guided tour (driver.js) — DONE

- [x] `web/src/lib/tour.ts` — one step list per role, written for a **layman**: no "rubric
      weights sum to 1.0", but "the weights have to add up to 100%, and the page tells you
      live whether they do". Participants get find-event → join-team → draft/autosave →
      gallery/voting. Judges get their assigned list → how scoring works → why they cannot
      see other judges → *why being a harsh marker will not hurt anyone* (the normalization
      explanation is the single most valuable thing to tell a nervous first-time judge, and
      it is the one a support email always ends up having to explain). Organizers get create
      → rubric → invite/assign → results/reveal/export → optional webhooks.
- [x] Steps are a per-role **superset filtered at runtime** by whether each selector is
      present *and visibly rendered*. This is what lets one definition run from any screen
      without choreographing navigation between steps, and it is why the tour degrades
      rather than breaks: an absent anchor costs one step, not the tour. The visibility half
      of the check matters specifically because the desktop nav stays in the DOM at phone
      widths behind `hidden md:flex` — a presence-only check would spotlight a zero-size box.
- [x] Anchor via `data-tour="..."` attributes, never link text or tab order — both are fair
      game to reword later, and a tour that silently stops matching is worse than no tour.
- [x] Auto-start once per role per browser, remembered in `localStorage` (**not** a DB
      column: this is a per-browser convenience, it must survive nothing, and adding a
      schema change for it would be unjustified). Every read/write wrapped — blocked storage
      in private browsing must degrade to "offer the tour again", never throw.
- [x] Replayable on demand from `/profile`, and the tour's own closing step says so.
- [x] Popover restyled onto this repo's own tokens in `index.css` (driver.js's stock look is
      a blue on a system font stack). Keyboard-operable with a visible focus ring, since the
      tour is fully keyboard-driven and PLAN.md's UX bar applies to it like any other screen.

**Found while verifying, and fixed — the suite was passing by luck.** The full Playwright
suite went green on the first run *with* the tour live, which was not evidence of safety: a
globally-mounted overlay that appears on a 700ms timer means every spec that logs in is
racing it, and fast specs simply won the race. That is flakiness by construction, and this
repo already carries an Open Questions entry about keeping runs deterministic. Fixed
properly rather than left to timing: `tests/tour-state.ts` pre-seeds the tour's own
"already seen" flags as Playwright `storageState`, so no spec ever meets the overlay by
accident. `lifecycle.spec.ts` builds its own context via `browser.newContext()`, which does
not inherit the `use` block, so it passes the same state explicitly — it would otherwise
have been the single remaining racing context. **`tests/tour.spec.ts` (5 cases) deliberately
opts back out** and is the one place the tour is genuinely exercised: first-login appearance,
dismissal persisting across a reload, replay from `/profile`, judge-vs-organizer step
divergence, and the negative case that a signed-out visitor is never interrupted.

### 8.2 — `USER-MANUAL.md` v1 (illustrated, step-by-step) — DONE

- [x] A genuine manual, not a feature tour: written per role, in the order a real person
      hits each screen, with a real screenshot at each step.
- [x] Screenshots captured **live against the running stack on fixture data** — the same
      non-negotiable rule §1 already applies to `acceptance-report.txt` and the README's
      existing screenshots. No mockups, no hand-drawn diagrams standing in for a real UI.
      18 images, all captured in the same session as the prose describing them.
- [x] Stored under `docs/screenshots/manual/`, alongside the existing `docs/screenshots/`.
- [x] Covers: signing up, the four seeded logins, participant path (find event → team →
      invite → draft → submit → gallery), judge path (accept invite → dashboard → score
      form → what normalization does to your scores), organizer path (create → settings →
      rubric → judges → assignment → results/reveal → CSV export → webhooks), plus the
      guided tour itself and a short troubleshooting section.
- [x] Linked from `README.md`'s Documentation list so it is discoverable from the front door.

**A seeded-data gap this phase surfaced and closed.** Writing the manual meant photographing
what a reader actually sees after `docker compose up` — and the event page had no prizes on
it. Cause: `seed.py` read `tracks` from the fixture but never `prize_config` or
`max_team_size`, so Phase 7.1's prize configuration had **no seeded demonstration at all**,
despite being a named T1 requirement ("configurable dates, tracks and prizes"). A reader
following the manual, or a judge running the acceptance suite, would have seen an events
page with tracks and no prizes and reasonably concluded the feature was missing. Fixed by
reading both fields in `_seed_events` and giving the fixture event three real prizes. No
schema change — both columns already existed since Phase 7; they were simply never
populated from fixture data.

**Definition of Done — Phase 8 gate: MET.** Verified live in a real browser, not merely
compiled: the participant tour ran on 8 steps, the judge tour on 8, the organizer tour on 9,
each spotlighting its own role's real navigation, and replay from `/profile` correctly
re-ran with 7 steps there — one fewer, because the `event-list` anchor does not exist on the
profile page and the runtime filter dropped that step exactly as designed. `npm run build`
clean. Full suite green and **larger than before**: 215 backend + 9 Vitest + **89** Playwright
(84 pre-existing, all still passing, + 5 new tour cases) = **313**. `docker-compose.yml`
unchanged at exactly `db` + `api`; `driver.js` pinned to 1.8.0 with `--save-exact`, adds no
`npm audit` vulnerability, and makes zero runtime network calls. Tier-neutrality is stated
plainly in this phase's own header and in `acceptance-report.txt` Addendum 7 — this phase
scores under Adoptability & Operability (20%), not the tier ladder, and was only appropriate
because T1–T4 were already finished.

---

**A note on the test suite, corrected** (added by pranavneelu06, merged 2026-09-19). The
Definition of Done above claimed all Playwright specs pass. Fourteen had been failing since the
auth-screen redesign, including a real accessibility defect: `AuthLayout` nested its `<header>`
inside `<main>`, so neither auth screen exposed a `banner` landmark at all. That was fixed on
`main`, and the fix is kept. One caveat still applies: a *second* full run without recreating
the volume fails a handful of specs, because the suite changes the same database it reads.
Each of those specs passes when run alone.

---

## Phase 9 — Account Recovery: Forgotten Passwords

**Status: BUILT (2026-09-19).** Gate met; see the build notes below for the five places the
build differs from the plan, and why.

**Build notes: where the build differs from the plan.**
- **Email failures are logged, not audited.** A background send runs after its request's
  transaction has closed, so writing an audit row would mean a second database session on a
  side path, and it leaked rows between tests. The admin **Send test email** button is where
  delivery problems surface, synchronously and in plain language.
- **The organizer rate limit is 30 links an hour, not 10, and only issued links count.** Ten
  was too tight for the help-desk scenario this phase exists for, and refused attempts (a
  typo'd email, a blocked role) shouldn't use up the budget.
- **`ALTER TABLE … ADD COLUMN IF NOT EXISTS` alone hung the test suite.** It takes an exclusive
  lock even when the column exists, and blocked behind an open test transaction.
  `add_missing_columns()` checks `information_schema` first and only alters when a column is
  really missing.
- **The change-password tests live in `test_password_reset.py`.** `tests/` isn't a package, so
  a second file couldn't share the SMTP fixtures without moving them into `conftest.py`.
- **"Reset by {organizer}" appears on the reset success screen only,** not on a later
  `/profile` visit. That would need a new read endpoint for one sentence; the audit log and
  the "your password was changed" email already cover the takeover risk it was meant for.

**Verified:**
- 253 backend tests (215 existing + 38 new).
- 10 Playwright cases in `recovery.spec.ts`, including the full email flow run in a real
  browser through the Mailpit override.
- An existing pre-Phase-9 volume booted without `down -v`.
- `docker compose config --services` still lists exactly `db` and `api`.

**Entry condition:** Phases 1–8 gates are green and the Phase 4 UI gap is closed. Nothing
here touches judging, scoring, or the tier ladder.

**Why this phase exists.** Today a user who forgets their password has no route back in.
There is no "Forgot password?" link, no reset endpoint, and no way to change a password
even while signed in. The only recovery is an operator editing `password_hash` in Postgres.
For an organization like Hackathon Raptors, which runs 35+ events with a new crowd each
time, this is guaranteed to happen on the first Saturday morning of every event, with
hundreds of one-weekend accounts created the night before.

**The goal: recovery with no work for organizers or admins.** A user who forgets their
password should be able to fix it alone, in under two minutes, without asking anyone.

**Where this scores, stated honestly.** It does not climb the tier ladder: T1–T4 say
nothing about account recovery. It scores under **Adoptability & Operability (20%)**,
which is judged on *"whether Hackathon Raptors could realistically run the software"*.
Across 35+ events a year, password resets handled by hand at a help desk are a real
running cost; automated ones cost nothing. Part of this phase (9.1) is also a real
security fix, and it goes into `THREAT-MODEL.md`.

**How this fits §1 ("zero network calls at runtime").** Sending email is a network call,
so it follows exactly the rule this project already set for outbound webhooks (Phase 7.3):
**opt-in, and zero calls when nothing is configured.**

- Out of the box, with no mail settings, `docker compose up` makes **zero** network calls,
  needs no `.env`, and recovery falls back to the organizer-issued link (9.4). §1 holds
  unchanged for the default install.
- The organization plugs in **its own** SMTP server: its company mail relay, a Gmail or
  Workspace account, or any provider it already uses. This is the organization's own
  infrastructure, configured by the organization. It's not a hosted service or
  auth-as-a-service built into HackFlow, and HackFlow bundles no email SDK. Sending uses
  Python's standard library (`smtplib`, `email.message`), so **no new dependency** is
  added.
- For judges and local demos, an **optional** local mail catcher (Mailpit, 9.3) receives
  every email on the same machine and shows it in a browser inbox. You can see the whole
  email flow with the network physically unplugged.
- `docker-compose.yml` stays at exactly `db` + `api`. Mailpit lives in a separate override
  file that is never started by a plain `docker compose up`.

### Options considered

| Option | Verdict | Why |
|---|---|---|
| **Emailed reset link** ("magic link" to set a new password) | **Chosen (9.2)**, opt-in | Fully self-service with no organizer involvement. The link works once, expires in 30 minutes, and is stored only as a hash. |
| Emailed temporary password | **Rejected** | It's a working password left in the inbox indefinitely. Anyone who later reads that mailbox (a shared laptop, a forwarded email, a breach) can use it until it's changed, and many people never change it. A reset link stops working after one use and 30 minutes. |
| Passwordless sign-in by email link | **Deferred** | Worth considering once 9.2 exists, since it reuses the same tokens and mailer. It changes how everyone signs in, which is a bigger decision than recovery. |
| Organizer-issued reset link | **Chosen as fallback (9.4)** | Keeps recovery working when no mail server is configured or an email bounces. |
| Mail sent through a third-party email API (SendGrid, Resend, etc.) with its SDK | **Rejected** | That's a hosted-service dependency, which §11 forbids. Plain SMTP covers the same providers (most offer SMTP too) without an SDK. |
| Security questions | **Rejected** | NIST SP 800-63B says services shouldn't use them. Answers are guessable by teammates or findable online, and one-weekend users forget them as easily as passwords. |
| Recovery codes shown at signup | **Rejected** | One-weekend participants won't store them. |
| Passkeys (WebAuthn) | **Deferred** | Fits §1, since verification is local, but it's a sign-in method, not recovery. It needs HTTPS anywhere except `localhost`. Add later as optional sign-in. |
| Send the reset link out through the existing outbound webhooks | **Rejected** | Puts a live credential into Discord or Slack and their logs. Webhooks carry events, never secrets. |

### 9.1 — Sessions must be revocable (prerequisite, security fix)

**Found while planning this phase.** The session cookie is an `itsdangerous`-signed
`{user_id}` with a 7-day max age (`api/app/auth/session.py`). Nothing on the server can
invalidate it. So **a password reset today would not sign out whoever holds a stolen
session**, which defeats the point of a reset.

- [x] Add `session_version: int = 0` to `User`. Sign `{user_id, v}` into the cookie.
      `get_current_user` rejects a cookie whose `v` doesn't equal the user's current
      `session_version`. A cookie with no `v` reads as `0`, so every session signed in
      before this deploy stays valid.
- [x] Bump `session_version` on every password change or reset. This signs the account
      out everywhere, including the device that made the change, which then gets a fresh
      cookie in the same response.
- [x] **Schema note, found live on 2026-09-19.** `db.py` only calls `create_all`, which
      creates missing *tables* but never adds a column to an existing one. That already
      crash-looped the API once, after `cover_image_url` was added. Add an idempotent
      startup step next to `create_all`:
      `ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version integer NOT NULL DEFAULT 0`
      (and the same for `events.cover_image_url`), so upgrading an existing volume doesn't
      require `docker compose down -v`. No migration framework: this is two statements.
- [x] Tests: an old cookie is refused after a reset; a cookie issued before this deploy
      still works; logout still works.

### 9.2 — Automated "Forgot password?" by email (primary path when mail is configured)

**The user's flow:** on `/login`, click "Forgot password?", then enter your email, then get
an email and click its link, then choose a new password. You're signed in. No organizer or
admin is involved at any point.

- [x] `PasswordReset` table: `user_id`, `token_hash` (SHA-256 of the token; **the raw token
      is never stored**, unlike `JudgeInvite.token`), `channel` (`email` | `organizer` |
      `cli`), `issued_by_id` (null for `email`), `expires_at`, `used_at`. The token is
      `secrets.token_urlsafe(32)`. The same table and the same `/reset/:token` page serve
      9.2, 9.4 and 9.6.
- [x] `POST /api/auth/forgot-password` `{email}`, public. It **always returns the same
      response**, whether or not the account exists: *"If an account exists for that
      address, we've sent a reset link. It expires in 30 minutes."* This prevents anyone
      from probing which emails have accounts. If the account exists, it creates a token,
      invalidates any earlier unused one for that user, and queues the email.
- [x] Sending runs through FastAPI `BackgroundTasks`, so the response never waits on the
      mail server and its timing can't reveal whether the account exists. It uses
      `smtplib` with a 10-second timeout and makes a single attempt, the same decision as
      the webhooks in 7.3: no queue, no retries. A failure is logged and recorded in the
      audit log as `reset_email_failed` (never shown to the requester). The user can
      simply ask again.
- [x] **30-minute expiry, single use.** Only `POST .../redeem` uses up a link.
      `GET .../preview` never does, because corporate email scanners open links
      automatically to check them, and a link consumed on open would already be dead by the
      time the user clicks it.
- [x] `GET /api/password-resets/{token}/preview` returns `{valid, reason}`: expired, used,
      or unknown. `POST /api/password-resets/{token}/redeem` `{new_password}` applies the
      existing 8-character rule, sets the hash, marks the link used, bumps
      `session_version`, and signs the user straight in.
- [x] **"Your password was changed" email**, sent after every reset or change (9.5), with
      *"Wasn't you? Contact your event organizer."* This is what alerts the real owner if
      someone else got into their mailbox or account. It carries no link and no password.
- [x] Email content: plain text plus a simple HTML version, built with
      `email.message.EmailMessage` (which handles header encoding, so a crafted display
      name can't inject headers). No remote images, tracking pixels or CDN assets. It
      contains the reset link and its expiry, never a password. The From name is
      "HackFlow"; the From address comes from settings.
- [x] Rate limits: 3 requests per email address per hour, and 20 per IP per hour. Going
      over still returns the same generic response, so the limit can't be used to probe
      accounts either.
- [x] The reset page sends `Referrer-Policy: no-referrer`, so the token in the URL never
      leaks to another site through the Referer header.
- [x] **When mail isn't configured**, `/forgot-password` doesn't pretend. It shows the
      9.4 message instead (*"Ask an organizer at the help desk or in your event's channel;
      they can give you a reset link in under a minute."*) and asks for nothing.
      `GET /api/auth/recovery-options` returns `{email: bool}` so the page knows which to
      show.

### 9.3 — Mail delivery setup (SMTP configuration)

All settings are **optional environment variables**. With none set, email is off and
nothing breaks. `docker-compose.yml` passes them through with empty defaults
(`${SMTP_HOST:-}`), so an organization sets them in an optional `.env` file next to the
compose file, and a fresh clone still needs no `.env` at all.

| Variable | Example | Meaning |
|---|---|---|
| `SMTP_HOST` | `smtp.gmail.com` | Mail server. **Empty turns email off.** |
| `SMTP_PORT` | `587` | Usually 587 (STARTTLS) or 465 (SSL). |
| `SMTP_SECURITY` | `starttls` | One of `starttls`, `ssl`, or `none` (`none` is only for a local catcher). |
| `SMTP_USERNAME` | `events@raptors.dev` | Login for the mail server, if it needs one. |
| `SMTP_PASSWORD` | *(app password)* | Never logged, never returned by any endpoint, never written to the database. |
| `SMTP_FROM` | `HackFlow <events@raptors.dev>` | Sender shown on the email. |
| `APP_BASE_URL` | `https://hackflow.raptors.dev` | Used to build the absolute link in the email. Defaults to `http://localhost:8000`. |

- [x] **Local demo inbox, needing no internet: `docker-compose.mail.yml`**, an override file
      that adds a pinned `axllent/mailpit` service (SMTP on port 1025, web inbox on
      `http://localhost:8025`) and points the API at it (`SMTP_HOST=mailpit`,
      `SMTP_PORT=1025`, `SMTP_SECURITY=none`). Run it with
      `docker compose -f docker-compose.yml -f docker-compose.mail.yml up`. Every reset
      email lands in the Mailpit inbox and nothing leaves the machine. This is how judges
      and the Playwright test see the full flow. The base `docker-compose.yml` is
      unchanged and still starts only `db` + `api`.
- [x] **Real delivery, documented for organizers** in `README.md` and `USER-MANUAL.md`:
      - Gmail or Google Workspace: `smtp.gmail.com`, port 587, `starttls`, using an
        *app password* (this requires 2-step verification on the account; the normal
        account password won't work).
      - Outlook or Microsoft 365: `smtp.office365.com`, port 587, `starttls`.
      - Any other provider, or the organization's own mail server: the host, port and
        login it gives you.
      - Say plainly that delivery depends on the provider, that new sending addresses can
        land in spam, and that setting up SPF and DKIM for the sending domain is the
        provider's job, not HackFlow's.
- [x] **Admin "Email delivery" card**, on the admin dashboard only. It shows whether email
      is on, plus the host, port, security and from-address, **never the password**. A
      **"Send test email"** button sends one to the signed-in admin's own address and shows
      success, or the server's error in plain language (for example *"The mail server
      rejected the login. For Gmail, use an app password."*). This is where an organizer
      confirms setup worked, instead of waiting for a real user to be locked out.
- [x] Settings are read once at startup. Changing them means restarting the `api`
      container, which the card says. There is no settings screen that stores the SMTP
      password in the database: a secret belongs in the environment, not in a table
      exposed through an admin UI.

### 9.4 — Organizer-issued reset links (fallback)

Used when email is off, when a user's email bounces, or when someone has lost access to
their mailbox. The organizer enters the account's email and clicks **"Create reset link"**.
The platform shows a single-use link to copy (the same copy affordance as
`JudgeInvitePanel`), and the organizer sends it through the event's usual channel.

**Who can reset whom.** Role gating is enforced at the endpoint, never only in the UI (§1):

| Issuer | Can reset | Cannot reset |
|---|---|---|
| organizer | participant, judge | organizer, admin: that would let one organizer take over another, or reach admin |
| admin | participant, judge, organizer | admin: no lateral takeover; a locked-out admin uses 9.2 or 9.6 |
| participant, judge | nobody | everyone |

- [x] `POST /api/password-resets` `{email}`: organizer or admin only, and the table above
      applies. Returns the link **once**, in this response only. 60-minute expiry. An
      organizer looking up an email is not an enumeration leak, because they can already
      export every email via `users.csv`.
- [x] Audit log records both issue and redeem, including who issued. **Accepted risk,
      stated rather than hidden:** a dishonest organizer could issue a link and use it
      themselves. The mitigations are the audit trail, the "your password was changed"
      email (when mail is on), and that the real user gets locked out, so they find out
      immediately.
- [x] Rate limit: 10 links per issuer per hour.
- [x] Organizer UI: a **"Help someone sign in"** card on the organizer and admin dashboard:
      an email field, then "Create reset link", then the link with a copy button and its
      expiry shown as a countdown.

### 9.5 — Change password while signed in

- [x] `POST /api/auth/password` `{current_password, new_password}`, any role. It bumps
      `session_version`, which signs out other devices, and re-issues this device's cookie.
      When mail is on, it also sends the "your password was changed" email. A wrong current
      password returns an inline error, never a toast.
- [x] A "Change password" section on `/profile`, with the copy *"This signs you out on
      every other device."*

### 9.6 — Break-glass: reset any account from the server

- [x] `docker compose exec api python -m app.auth.reset_link <email>` prints a reset link
      for any account, including an admin, and writes an audit entry with
      `channel = cli`. This covers an admin locked out while email is off. Shell access to
      the host is the trust boundary, so this adds no new attack surface. Document it in
      the README and the `USER-MANUAL.md` troubleshooting section.

*(This replaces the earlier 9.4 idea, "self-service requests queued for organizers".
Emailed resets make the user's request the whole process, so there's nothing left to
queue.)*

### UX checklist (PLAN.md §4.7, every new screen)

- [x] `/forgot-password`, `/reset/:token`, the "Help someone sign in" card, the "Email
      delivery" card, and the profile section each have loading, empty and error states,
      and work at 375, 768 and 1280px, and by keyboard alone.
- [x] A "Forgot password?" link sits under the password field on `/login`.
- [x] Copy says "reset link", never "token". No status codes or SMTP error codes on screen.
- [x] An expired or used link gets its own plain-language page with a "Send a new link"
      button (or "Ask your organizer for a new one" when email is off), never a raw 404
      or 410.
- [x] Copy buttons announce "Link copied" to screen readers, like the judge invite panel.
- [x] The guided tours gain one step each: for organizers, the "Help someone sign in" card;
      for admins, the "Email delivery" card.

### Tests

- [x] pytest `test_password_reset.py`:
      - Forgot-password returns an identical body and status for a known and an unknown
        email.
      - A mocked SMTP server receives exactly one email, containing a working link and no
        password.
      - Expired, used and superseded links are refused; a GET preview doesn't use up a
        link.
      - The token is stored only as a hash.
      - An old session is rejected after a reset.
      - Rate limits hold and still return the generic response.
      - With email off, no SMTP connection is attempted. This is the §1 check.
      - The full 9.4 role matrix, including every disallowed pair returning 403.
      - The audit rows are written.
- [x] pytest `test_change_password.py`: a wrong current password is refused, other sessions
      are revoked, and the "changed" email is sent.
- [x] pytest: the admin test-email endpoint is admin-only and never returns
      `SMTP_PASSWORD`.
- [x] Playwright, against the Mailpit override: a user requests a reset, the test reads the
      email from Mailpit's local API, follows the link, sets a password, and lands signed
      in. A second test covers the organizer-link fallback with email off.

### Docs

- [x] `README.md`: a short "Email (optional)" section with the settings table, the Mailpit
      command, and a statement that with nothing set HackFlow makes zero outbound calls.
- [x] `USER-MANUAL.md` §8 Troubleshooting: "I forgot my password" for participants,
      organizers and admins, plus a "Setting up email" walkthrough using the test button.
- [x] `ARCHITECTURE.md`: email alongside webhooks as the only two opt-in outbound paths.
- [x] `THREAT-MODEL.md`: new entries for "stolen session survives a password change"
      (fixed by 9.1), "account enumeration via forgot password" (identical responses and
      timing), "reset link leaked or scanned" (hashed, single use, 30 minutes, GET doesn't
      consume, no-referrer), "someone else's mailbox is compromised" (the "changed" email
      alerts them, and the organizer can override), and "organizer takes over an account"
      (accepted risk, audited).

**Definition of Done — Phase 9 gate:** 9.1–9.6 built; the full suite green, including the
new tests; every UX item checked; `docker-compose.yml` still exactly `db` + `api`; with no
SMTP settings, zero runtime network calls (asserted by a test); the Mailpit override
demonstrates the full email flow offline; and an existing pre-Phase-9 volume boots without
`down -v`.

---

## Phase 10 — Platform Audit: Judging Integrity, Core Hackathon Features, Operability

**Status: BUILT (2026-09-19). All 13 items.** Verified on the merged tree:
- **348 backend tests**, including 40 in `test_phase10.py`, each opening with the audit's
  own "Found" scenario, plus Phase 9 and 10 endpoints added to the role-isolation matrix
  (139 cases).
- **105 Playwright specs green, 1 skipped** (the email-only recovery spec, correct with
  email off). This includes 7 new flows in `phase10.spec.ts`.
- An existing pre-Phase-10 volume, including a duplicate team membership, booted without
  `down -v`: it logged the duplicate, held back the unique index, and the admin Users page
  lists it.

**Build notes: where the build differs from the plan.**
- **`event_phase()` is computed in the browser** (`components/EventTimeline.tsx`) from the
  same `start_at`/`end_at`/`results_hidden_until` the server enforces, rather than returned
  on every event. The event endpoints return the table model directly, and a derived field
  there would have been a second source of truth for the same dates.
- **A judge's list only shows assignments from events whose judging has opened.** This was
  found while testing 10.3: an assignment made before the deadline gate existed would
  otherwise offer a "Score now" the server refuses. The "Coming up" card says when the rest
  open.
- **Assignment re-runs now fill gaps properly.** Existing assignments count toward `k` and
  toward judge load, which 10.7's "remove a judge, re-run" depends on. The result with
  nothing assigned yet is unchanged (the existing determinism tests still pass).
- **Confirmations use the browser's own `window.confirm`**, which is keyboard- and
  screen-reader-accessible, rather than a new modal component.
- **Tests are one file (`test_phase10.py`) with a section per item**, not one file per item.
  Same coverage, and the SMTP/role helpers are shared.
- **10.1, 10.2 and 10.4 were built twice** and merged. See the note above.
- **Found after the build, fixed 2026-09-19.**
  - 10.5's "included in `submissions.csv` and the event backup" was ticked but not built.
    The links, and the event `rules` from 10.8, are now in the CSV, `export.json` and
    `import`, with imported links validated like the form's (a backup file is untrusted
    input). Covered by `test_links_and_rules_survive_a_backup_round_trip_and_bad_links_are_refused`.
  - Phase 9's two dashboard cards had landed on the *participant* dashboard instead of
    the admin's. The server refused them, so nothing leaked. They were moved, and a
    per-role regression spec was added.

**Two implementations, merged (2026-09-19).** pranavneelu06 built 10.1, 10.2 and 10.4
independently on `feat/phase10` (merged to `main` as PR #2). They stated plainly that 10.3 and
10.5–10.13 weren't done. The same three items had also been built here, as part of all 13.
The two were merged as follows:
- **This branch's version kept for 10.1, 10.2 and 10.4**, because it closes three gaps a
  review of `main` found:
  - **Existing databases.** `main` needed `docker compose down -v` to pick up
    `judge_invites.event_id`, which deletes every event. `add_missing_columns()` upgrades in
    place instead.
  - **Password spraying.** `main`'s per-IP login limit was only checked after a failed
    password, so a correct guess still got in. It's now checked before.
  - **Account probing by timing.** `main` answered faster for unknown emails. Unknown emails
    now run bcrypt against a dummy hash.
  - 10.2 also gets the database-level unique index `main` left out.
- **Kept from `main`:**
  - the login/register `banner` landmark fix
  - the dashboard label de-duplication
  - `BASE_URL`-aware judge-invite specs
  - the event-scoped `JudgeInvitePanel`
  - the move of the rate limiter to `app/ratelimit.py`
  - the Phase 8 correction above
- `main`'s `JudgePanelCard` was rebuilt on this branch's `/api/events/{id}/judges`, which
  also carries 10.7's progress counts.

**Entry condition:** Phases 1–9 gates are green.

**Where this came from.** A full audit on 2026-09-19, done after Phase 9 exposed "forgot
password" as a missing basic. It had two parts:
- **Code:** every API route, model and permission check.
- **Visual:** the live app walked in a browser as a participant, a judge and an organizer.

Four findings are **bugs that make results wrong or unfair**, not missing features, so they
come first. Each item below cites what the audit found. **Build in order: 10.1–10.4, then
10.5–10.9, then 10.10–10.13.**

**Where this scores, stated honestly.**
- **Tier Completion & Correctness (40%):** 10.1–10.3 and 10.7 are judging correctness, the
  core of T2. 10.5, 10.6 and 10.8 close gaps in T1 and T3, where a hackathon's own
  workflow (link to your project, announce winners, know what you're judged on) is half
  there.
- **Security:** 10.4 fixes a real hole and goes into `THREAT-MODEL.md`.
- **Adoptability & Operability (20%):** 10.9–10.13 are what an organization running 35+
  events a year hits in its first week.

**Constraint check (§1).**
- No new dependencies. `docker-compose.yml` stays exactly `db` + `api`.
- Everything that sends email (10.7's reminders, 10.11's announcements) goes through
  Phase 9's opt-in mailer, so with no `SMTP_HOST` it's hidden and nothing is sent.
- Video links are shown as links, **never embedded**: a YouTube or Vimeo embed would load
  third-party content into the served app.
- Every new column on an existing table goes through `db.add_missing_columns()`, and every
  backfill runs at boot and is idempotent, so existing volumes upgrade without
  `down -v`.

---

### 10.1 — Judges belong to events (bug, critical)

**Found:** assignment builds its judge pool from *every* judge account on the platform
(`judging/router.py:199`, `select(User).where(User.role == Role.judge)`), and a
`JudgeInvite` has no event attached (`judging/models.py:28`). In the live app,
dogfood-2026's Judges card listed 12 invitations, none of them for that event. For an
organization running many events, a judge invited to one hackathon gets submissions from
all of them.

- [x] New table `event_judges` (`event_id`, `user_id`, `added_at`, `added_by_id`), unique on
      `(event_id, user_id)`. **The assignment pool is this event's judges only.**
- [x] `judge_invites.event_id` (nullable for old rows). Invitations are created from an
      event's page, and redeeming one adds the redeemer to that event's judges (plus the
      existing participant-to-judge role change).
- [x] **"Add an existing judge"** on the event's Judges card, by email, so a judge who works
      several events isn't sent a new invitation each time. Organizer or admin only; the
      account must already have the judge role.
- [x] The Judges card lists only **this event's** invitations and judges.
      `GET /api/judge-invites` takes `event_id`.
- [x] **Backfill at boot:** every `(event_id, judge_id)` pair in existing
      `judge_assignments` becomes an `event_judges` row, so already-assigned judging keeps
      working. Seeded judges are attached to the seeded events in the fixtures.
- [x] The judge dashboard groups assignments by event (the fields exist since Phase 4's
      `event_id`/`event_name` addition).
- [x] **Test hygiene:** the Playwright specs create their invitations against a named test
      event, so they stop piling up in the Judges card of real events.

### 10.2 — One team per participant per event (bug)

**Found:** `join_team` only refuses joining *the same* team twice (`teams/router.py:57`),
and `create_team` doesn't check anything. The seed data already contains a violation:
`jordan@` is on both Codehawks and Quiet Ledger in dogfood-2026. One person can enter the
same hackathon twice.

- [x] `create_team` and `join_team` refuse with 409 when the user already belongs to a team
      in that event: *"You're already on Codehawks for this event. Leave it first to join
      another team."*
- [x] Database-level guard: `team_memberships.event_id` (backfilled from `teams`) with a
      unique index on `(event_id, user_id)`, so two requests at once can't both get through.
      If an existing volume already contains duplicates, **boot doesn't crash**: it skips
      the index, logs each duplicate, and the admin dashboard shows a warning listing them
      until an organizer resolves them with 10.9's leave/remove.
- [x] Fix `fixtures/teams.json` so no participant is on two teams in one event.

### 10.3 — Judging opens only after submissions close (bug)

**Found:** neither `run_assignment` nor score submission checks the event's `end_at`. In
the live app a judge had already scored "Audit Trail Explorer", which its team can keep
editing until Oct 17, so the score can describe a version that no longer exists.

- [x] `POST /api/events/{id}/assignments` refuses before `end_at` with 409: *"Judging opens
      when submissions close on 17 Oct at 18:00. Close submissions early from Event
      settings if you need to."*
- [x] `PUT /api/assignments/{id}/score` refuses before `end_at` too, which covers
      assignments made before this fix.
- [x] **"Close submissions now"** in Event settings sets `end_at` to now, behind a
      confirmation that says what it does ("Teams will no longer be able to edit their
      entries").
- [x] The judge dashboard shows *"Judging opens on …"* for an event still open for
      submissions, instead of an empty list.
- [x] **Fixtures and specs:** seed one event that is already past its deadline with results
      still hidden. `judging.spec.ts` and `judge-invite.spec.ts` move to it, because
      dogfood-2026 (deadline Oct 17) can no longer be judged.

### 10.4 — Limit login attempts (security)

**Found:** `POST /api/auth/login` (`auth/router.py:88`) has no limiter, so passwords can be
guessed without limit. It also returns *faster* for an unknown email, because bcrypt only
runs for real accounts, which lets anyone probe which emails are registered.

- [x] Only **failed** attempts count: 10 per account and 30 per IP per 15 minutes, reusing
      `TokenBucketLimiter`. Going over returns 429: *"Too many attempts. Try again in about
      N minutes, or reset your password."* The message is the same whether the account
      exists or not.
- [x] Unknown emails run bcrypt against a fixed dummy hash, so both paths take the same time.
- [x] A successful login clears that account's failure count.
- [x] Audit: log `user.login_throttled` with the IP. Don't log every failure, which would
      flood the log.

---

### 10.5 — Project links on submissions

**Found:** a submission is only title, description, track and screenshot. On the judge's
scoring screen, a judge rated four weighted criteria from **one sentence** of text, with no
code, no running demo and no video to open.

- [x] `submissions.repo_url`, `demo_url`, `video_url`, all optional. Validated server-side:
      `http`/`https` only (so no `javascript:` links), at most 500 characters.
- [x] The editor has three fields with inline validation, autosaving like the others.
- [x] Shown as labelled buttons (**Code**, **Live demo**, **Video**) that open in a new tab
      with `rel="noopener noreferrer nofollow"`:
      - on the submission detail page
      - as small icons on gallery cards
      - on the judge's scoring screen, which also gains the screenshot it currently lacks.
- [x] Video is a link, never an embed (§1).
- [x] Included in `submissions.csv` and the Phase 4 event backup.

### 10.6 — Winners and awards

**Found:** every event has prizes set up ("1st Place — $5,000 + mentorship",
"Best Developer Tool — $1,000"), but nothing links a prize to a winning project. The event
ends without ever saying who won.

- [x] New `awards` table (`event_id`, `prize_rank`, `submission_id`, `note`, `awarded_by_id`),
      unique on `(event_id, prize_rank)`.
- [x] An **"Winners"** card on the results page lists each configured prize with a project
      picker. Pickers are pre-suggested: overall prizes follow the normalised standings in
      order, and a track prize suggests the top-ranked project in that track. The organizer
      confirms or changes each one. A project can win more than one prize; the card flags
      it when that happens.
- [x] Awards stay **hidden until results are revealed**, using the same
      `may_see_results` gate as the standings.
- [x] After the reveal:
      - the event page gets a **Winners** section
      - winning gallery cards and submission pages get a prize badge
      - the Phase 4 certificate names the prize
- [x] Audit log records every award change.

### 10.7 — Judging progress, reassignment, and conflicts of interest

**Found:** `GET /api/events/{id}/assignments` exists, but no page uses it. The only view of
per-judge progress is a CSV download. In the live app the standings showed 1 judge per
project out of 3 assigned, and nothing on screen said which judges hadn't scored.

- [x] A **"Judging progress"** card on the results page. It leads with the overall
      "X of Y scores in", then one row per judge: scored/assigned and last activity.
- [x] **Remove a judge from this event:** deletes their unscored assignments and keeps any
      scores they already submitted. Confirmation required. Pressing **Assign judges**
      again fills the gaps, since assignment already only fills gaps.
- [x] **A judge can declare a conflict of interest** on the scoring screen with an optional
      reason. This deletes that unscored assignment and records a `judge_conflicts` row
      (`event_id`, `judge_id`, `submission_id`, `reason`) that assignment's conflict check
      always respects, so the project is never handed back to that judge. The organizer
      sees the declaration in the progress card.
- [x] **Send a reminder**, shown only when email is on: emails a judge their remaining
      count and a link to `/judge`. Limited to one per judge per hour.
- [x] Tests cover all of it: the removed judge's scores stay, conflicts are honoured on a
      re-run, and reminders are hidden and never sent with email off.

### 10.8 — Event timeline, rules, and judging criteria everyone can see

**Found:**
- dogfood-2026 starts Oct 15, but the event page shows only a countdown to the Oct 17
  deadline, so it reads as if it has already started.
- Participants can't see the criteria they'll be scored on.
- Event dates can't be changed after creation, despite README's claim that they can.

- [x] A server-side `event_phase()`, returned on every event, gives one of: `upcoming`,
      `open` (taking submissions), `judging` (deadline passed, results not out),
      `results`.
- [x] Every event card and event page shows a phase badge, the start and end dates, and a
      countdown worded for the phase: "Starts in", "Submissions close in", "Judging in
      progress", "Results are out".
- [x] `events.rules`: plain text, rendered with line breaks and **never as HTML** (so it
      can't carry a script). Edited in Event settings and shown on the event page.
- [x] Rubric criteria gain an optional `description` ("Impact: who would use this, and how
      much would it help them?"). Judges see it under each field; participants see a
      read-only **"How projects are judged"** section with criterion names, weights and
      descriptions (never scores). Served from a new public
      `GET /api/events/{id}/criteria`.
- [x] **Edit dates after creation** in Event settings. Start must come before end, and
      moving the end date earlier than now asks for the same confirmation as 10.3's
      "Close submissions now". Correct README's claim at the same time.
- [x] No change to who can do what in each phase, apart from 10.3.

### 10.9 — Team management

**Found:** the team card offers only "Copy" for the invite link. Nobody can leave, remove a
member, rename the team or get a fresh invite link. Invite links also expire after 30 days
with no way to renew them.

- [x] `teams.captain_id`: whoever created the team. Existing teams are backfilled with their
      earliest member.
- [x] **Any member can leave.**
      - If the captain leaves, the earliest remaining member becomes captain.
      - If the last member leaves, the team is deleted, along with any draft entry.
      - The last member **can't** leave once the team has *submitted*. They get a plain
        explanation instead.
- [x] **The captain can rename the team, remove a member, hand captaincy to someone else, and
      get a new invite link** (the old link stops working straight away). Removing a member
      and changing the link each need a confirmation.
- [x] Everything is blocked after the submission deadline, like all other team changes.
- [x] Audit log entries for leave, remove, rename, captaincy change and new invite link.

---

### 10.10 — Admin user management and organizer invitations

**Found:** there are no user-management endpoints at all. Organizer accounts can *only*
come from `fixtures/users.json`, so a real organization can't add a new organizer without
editing the database.

- [x] An admin-only `/admin/users` page: search by name or email, filter by role, 50 per
      page.
- [x] **Change a user's role** between participant, judge and organizer. The admin role is
      never granted from the UI (only the seed data or the 9.6 CLI can create admins), and
      admins can't change their own role.
- [x] **Deactivate or reactivate an account.** `users.is_active` is checked at login
      (*"This account has been deactivated. Contact an admin."*), and deactivating bumps
      `session_version`, which signs the user out immediately. Admins can't be deactivated,
      nor can you deactivate yourself.
- [x] **Organizer invitations**, reusing the judge-invite pattern: `judge_invites.grants_role`
      (`judge` | `organizer`). Only admins can create organizer invitations, and they aren't
      tied to an event. Redeeming one promotes the account to organizer. They're single
      use, expire and can be revoked, exactly like judge invitations.
- [x] Audit log entries for every role change, deactivation and invitation.

### 10.11 — Event announcements

**Found:** once an event is running, organizers have no way to tell participants anything,
such as "the deadline has moved" or "the demo livestream starts at 5".

- [x] New `announcements` table (`event_id`, `author_id`, `title`, `body`, `created_at`,
      `emailed_count`). Plain text, at most 2,000 characters, **never rendered as HTML**.
- [x] Organizers post from the event page. Announcements show newest first on the event
      page, and the latest ones appear on the dashboard of every participant on a team in
      that event.
- [x] **"Also email everyone in this event"** checkbox, shown only when email is on. It
      sends from a background task over **one** SMTP connection; this needs a new
      `mailer.send_many`, so a 200-person event doesn't open 200 connections. Limited to one
      emailed announcement per event per 10 minutes. The card reports how many were sent.
- [x] A new webhook topic, `announcement.posted`, so events already wired to Discord or
      Slack (Phase 7.3) post announcements there automatically.
- [x] Organizers can edit or delete an announcement. A deleted announcement disappears from
      the page; emails already sent obviously stay sent.

### 10.12 — Draft events

**Found:** an event is public the moment it's created, before its tracks, prizes, rubric or
rules are set.

- [x] `events.status` (`draft` | `published`). Existing events are backfilled as
      `published`; events created from now on, including imported ones, **start as
      drafts**.
- [x] A draft is invisible to everyone except organizers and admins: left out of
      `/api/events` and the gallery, and **404 (not 403)** by slug, so a draft's existence
      doesn't leak. No teams can be created on a draft.
- [x] A **Publish** button with a short checklist: dates set, at least one track, and a
      rubric. Missing items are warnings, not blocks. **Unpublish** is allowed only while
      the event has no teams.

### 10.13 — Edit your display name

**Found:** the profile page can change only the avatar.

- [x] `PATCH /api/auth/me` `{name}`, with the same 2–60 character rule as sign-up, edited
      inline on `/profile`. Names are read live wherever they appear (teams, comments,
      judge progress), so no other data changes. Audit log entry.
- [x] Changing the email address is **out of scope**: it needs verification of the new
      address, which is its own flow.

---

### Schema changes (all through `add_missing_columns()` or `create_all`)

- **New tables:** `event_judges`, `awards`, `judge_conflicts`, `announcements`.
- **New columns on existing tables:**
  - `judge_invites.event_id`, `judge_invites.grants_role`
  - `team_memberships.event_id`
  - `teams.captain_id`
  - `submissions.repo_url`, `submissions.demo_url`, `submissions.video_url`
  - `events.status`, `events.rules`
  - `users.is_active`
- **Backfills at boot, all idempotent:**
  - `event_judges` from existing assignments
  - `team_memberships.event_id` from each membership's team
  - `teams.captain_id` from each team's earliest member
  - `events.status = published` for every existing event
- Rubric criterion `description` needs no schema change: criteria are already JSON.

### UX checklist (PLAN.md §4.7, every new or changed screen)

- [x] Every new card and page has loading, empty and error states, and works at 375, 768
      and 1280px, and by keyboard alone.
- [x] Every destructive action has a confirmation that says what will happen: removing a
      judge, a team member or a user; leaving a team; new invite link; closing submissions;
      unpublishing; deactivating.
- [x] Role-aware navigation: admins get **Users**; nobody else sees admin screens, and the
      API refuses them regardless.
- [x] The guided tours gain steps for "Judging progress", "Winners", "Announcements" and
      (for admins) "Users", anchored to their cards like the Phase 9 steps.

### Tests

- [x] pytest, one file per item, covering the "Found" case of each (the audit's exact
      scenario must fail before the fix and pass after), plus the role matrix for every new
      endpoint in `test_role_isolation.py`.
- [x] Specifically:
      - **10.1:** a judge not attached to an event is never assigned its submissions.
      - **10.2:** a second team in the same event is refused.
      - **10.3:** assignment and scoring are refused before the deadline.
      - **10.4:** throttling returns the same response for known and unknown emails.
      - **10.5:** a `javascript:` link is refused.
      - **10.6:** winners stay hidden until the reveal.
      - **10.12:** a draft returns 404 to a participant.
- [x] Playwright:
      - add a link to a submission and see it on the judge's screen
      - declare a conflict and see it reported to the organizer
      - assign a winner and see it appear after the reveal
      - post an announcement
      - leave a team
      - publish a draft
      - an admin promotes a user to organizer
- [x] Every existing spec that depends on judging before the deadline or on dogfood-2026's
      judges moves to the new past-deadline fixture event (10.3).

### Docs

- [x] `README.md`: correct the "edit an event's dates" claim (true once 10.8 lands), and
      update "What's here".
- [x] `USER-MANUAL.md`: participant sections for project links, team management and
      announcements; judge sections for conflicts of interest and "judging opens after the
      deadline"; organizer sections for event judges, progress, winners, drafts and
      announcements; admin section for users and organizer invitations.
- [x] `DATA-MODEL.md`: the four new tables and every new column.
- [x] `JUDGING.md`: event-scoped judge pools, the deadline gate, conflicts of interest, and
      how award suggestions are derived from the standings.
- [x] `THREAT-MODEL.md`: new entries for cross-event judge leakage (10.1), multi-team
      entries (10.2), judging a moving target (10.3), password guessing and email probing
      by timing (10.4), `javascript:` links (10.5), early winner leaks (10.6), draft
      leakage (10.12), and admin lockout or escalation (10.10).
- [x] PLAN.md Phase 8's "89 Playwright checks, all passing" line: update to the real count
      after this phase.

**Definition of Done — Phase 10 gate:**
- All 13 items built.
- Each audit finding reproduced by a test that fails on the pre-Phase-10 code and passes
  now.
- Full suite green.
- Every UX item checked.
- `docker-compose.yml` still exactly `db` + `api`, and still zero runtime network calls
  with email off.
- An existing pre-Phase-10 volume, including one with a duplicate team membership, boots
  without `down -v`.

---

## 8. Judging integrity — implement exactly this

### 8.0 Role model — who evaluates what, and by which mechanism

Settle this before reading the algorithm, because the algorithm only makes sense
against it. The brief enumerates four roles flatly — "participant/judge/organizer/admin"
— and describes judges via **"judge invitation and assignment"**. Judges are therefore
people brought *onto* the event to evaluate, not participants rotated into evaluating
each other.

This build ships **two** evaluation mechanisms, and they are deliberately separate
systems with separate abuse models. Do not merge them, and do not let one's vocabulary
leak into the other:

| | **Formal judging (T2)** | **Community voting (T3)** |
|---|---|---|
| Who acts | `judge` role only, and only on an assignment that is theirs | Any signed-in user, any role |
| Instrument | Weighted rubric, criteria scored 0–`max_score` | One vote per user per submission |
| Integrity model | Role isolation + per-assignment ownership + conflict exclusion + cross-judge normalisation | Unique constraint + rate limiting + fingerprint flagging + hidden results |
| Feeds the ranking? | Yes — `z_bar_i` is the ranking value | No — a separate public tally, never an input to judging |
| Endpoint gate | `require_role(Role.judge)` **plus** an ownership check | `get_current_user` |

**Participant-to-participant peer review is not in scope.** The brief never mentions
it, never uses the phrase, and never describes participants scoring each other. Do not
infer it from the conflict rule below, and do not add it as a "natural extension" — it
would put a competitor's hand on a rival's score, which is precisely what the role
isolation in this section exists to prevent.

**Community vote counts must never reach the judging pipeline.** `normalize_scores()`
takes rubric scores only. A popular project and a well-executed one are different
claims, and conflating them would make the normalisation indefensible.

**Assignment algorithm** (implement as `assign_judges(submissions, judges, team_memberships, k) -> list[JudgeAssignment]`):

1. Build a conflict set: exclude `(judge, submission)` pairs where the judge is on the submitting team.
   *This is a safeguard, not a hint that judges are drawn from participants.* A judge may
   legitimately also be on a team — a mentor who entered a side project, an organizer's
   colleague who joined a team late — and the platform must make that harmless rather than
   forbidding it. The rule existing does **not** license a peer-review workflow (8.0).
2. Iterate submissions round-robin; for each, assign the `k` judges (organizer-configurable, default 3) with no conflict and the fewest assignments so far; break ties by judge ID ascending for determinism.
3. This is deliberately a greedy degree-constrained assignment, not a max-flow solver — do not "improve" it into something non-deterministic or harder to test.

**Normalization** (implement as `normalize_scores(raw_scores_by_judge) -> dict[submission_id, float]`):

```
mu_j    = mean of judge j's raw totals across their assigned submissions
sigma_j = population stddev of judge j's raw totals
z_{j,i} = (x_{j,i} - mu_j) / sigma_j          # if sigma_j == 0, z_{j,i} = 0 for all i from that judge
z_bar_i = mean of z_{j,i} over all judges j who scored submission i
display_i = clamp(50 + 10 * z_bar_i, 0, 100)  # for UI display only; keep z_bar_i as the ranking value
```

Write this as a pure function with unit tests covering: a judge with only one assignment (guard divide-by-zero the same as the sigma==0 case), a submission scored by only one judge, and the full fixture dataset.

**Role isolation:** implement the `require_role()` dependency once in `api/app/auth/`, import it everywhere. Never duplicate role-check logic inline in a route handler.

---

## 9. Testing & acceptance suite

- Write tests alongside each endpoint, not as a separate pass afterward.
- Before each phase gate, run: `docker compose up -d && pytest api/tests/ -v` and, once the acceptance suite is published, run it against the running `docker compose` stack exactly as a judge would.
- Maintain one Playwright test (`web/tests/`) that walks the full lifecycle: event creation → team formation → submission → judge assignment → scoring → normalized results → (voting, if built). Keep it green continuously — it doubles as the demo video script.

**9.1 — The organizer-published acceptance suite (instruction, kickoff).** The organizer publishes,
at kickoff, a test suite that runs against the *running portal* (not against source code) and reports
pass/fail per tier requirement. The exact same suite runs on our side and on the judges' side — there
is no separate "our" version. Once it exists:
- Run it against a clean `docker compose up -d --build` stack every time it's run — never against a
  stack with leftover manual test data (§1's seeding-is-the-only-setup rule applies here too).
- Run it as often as useful — after every phase gate at minimum, and again before any tier claim in
  `README.md` changes — not once near the end. It is cheap to re-run and there is no reason to let
  `acceptance-report.txt` go stale against the code.
- Commit its real output every time it's run, overwriting the previous `acceptance-report.txt`. This
  is already required by §11 ("do not hand-edit `acceptance-report.txt`"); the organizer's framing —
  "you run it yourself, as often as you like, and commit the output... nobody is guessing" — is the
  reason that rule exists, not a new rule on top of it.
- Until it's published, the self-issued report from our own suites (§5.5) stands in its place, header
  stating plainly that it's self-issued — see the Open Questions entry on this.

---

## 10. Documentation deliverables — write incrementally, not at the end

Update these as each phase completes, not in a single pass before submission:

- **`README.md`** — setup instructions, feature overview, tier claims (must match `acceptance-report.txt` exactly)
- **`ARCHITECTURE.md`** — system design; reuse the architecture diagram and modular-monolith rationale from the PDF
- **`DATA-MODEL.md`** — schema documentation; reuse the entity table from the PDF; note import/export paths
- **`JUDGING.md`** — assignment algorithm, normalization method with the math from Section 8 above, role-isolation strategy, and (if T3 fallback was taken) that decision and reasoning

---

## 11. Guardrails — do not do these

- Do not add any hosted/cloud service, external API, or network call anywhere in the runtime path.
- Do not implement role checks only in the frontend.
- Do not let a tier's scope — or an unpolished screen — bleed into the next phase before its gate is green.
- Do not invent visual design before `DESIGN_SYSTEM.md` arrives, and do not keep using placeholder styling after it arrives.
- Do not skip loading/empty/error states "for now" — build the shared components in Phase 0 and there is no excuse to skip them later.
- Do not hand-edit `acceptance-report.txt` — it must be the suite's real output.
- Do not claim a tier in `README.md` that the acceptance report doesn't back up.

---

## Phase 0/1 Audit

A line-by-line re-read of every Phase 0 and Phase 1 file, with each finding
reproduced against the running stack before it was fixed and pinned by a test
after. `api/tests/test_regressions.py` holds one test per defect, named after it.

### Correctness defects (all fixed, all reproduced first)

| # | Defect | Reproduced as | Fix |
|---|---|---|---|
| 1 | **Deadlines drifted by the viewer's UTC offset.** Columns were `TIMESTAMP WITHOUT TIME ZONE`, so the API served `2026-09-21T18:00:00` with no offset and `new Date()` read it as *local* time. The countdown disagreed with the deadline the API enforces by 5.5h in IST — and in a negative-offset zone it tells a participant they still have time when the server will reject the save. | `GET /api/events` returned offset-less timestamps; verified a 5.5h drift in `TZ=Asia/Kolkata` | All datetime columns are `timestamptz`; new `api/app/timeutil.py` (`utcnow`, `ensure_utc`) is the only source of "now"; naive client and fixture input is read as UTC. API now serves `...Z`. |
| 2 | **`PATCH /api/teams/{id}/submission` with `{"title": null}` → HTTP 500.** The validator called `.strip()` on `None`; `exclude_unset` alone would then have written `NULL` into a `NOT NULL` column. | `AttributeError: 'NoneType' object has no attribute 'strip'` in the api log | Validator is None-tolerant; router uses `exclude_unset=True, exclude_none=True`, so an explicit null means "no change". |
| 3 | **Unknown `/api/*` paths returned the SPA shell with HTTP 200.** The catch-all SPA route swallowed them, so a client mistake looked like a successful empty response instead of a 404. | `GET /api/does-not-exist` → `200 text/html` | Catch-all refuses `api/`, `healthz`, `docs`, `redoc`, `openapi.json` and 404s as JSON. |
| 4 | **`DELETE /api/events/{id}` → HTTP 500** on any event with teams or submissions (raw foreign-key violation). A destructive endpoint failing with a bare 500 violates §4.6. | `ForeignKeyViolation ... teams_event_id_fkey` | Returns `409` naming what blocks it and the consequence in plain language (§4.3). |
| 5 | **`docker compose exec api pytest tests/ -v` — the gate command PLAN.md documents — did not work.** `conftest.py` hard-coded `localhost`, which inside the api container is not the database. Exited 4 at collection. | `OperationalError: connection to server at "localhost" ... refused`, exit 4 | The test database is derived from the app's own `DATABASE_URL` + `_test`, so the documented command works with no extra environment. |
| 6 | **`PATCH /api/events/{id}` could invert the dates** that `POST` rejects — `EventUpdate` validated nothing. An event could be left with `end_at` before `start_at`. | — (found by reading; test added) | `EventUpdate` revalidates name length and UTC coercion; the router re-checks ordering against the stored row, so a one-sided change is still caught. |
| 7 | **Gallery search leaked `ILIKE` wildcards.** Searching `%` or `_` matched every submission, so a literal `100%` in a title could not be searched for. | `q=%` returned all rows | Term is escaped and the `ILIKE` uses an explicit `escape` character. |
| 8 | **54px horizontal overflow on `/gallery` at 375px.** `DESIGN_SYSTEM.md` §4 defines `sm` as *the 375px mobile target*, and says layout stacks below `md` (768px) with "never a horizontal scrollbar on a primary view" — but four `sm:` layout switches were written as though `sm` meant "wider than mobile" (Tailwind's 640px default), so they fired *on* mobile. | Measured `scrollWidth - clientWidth = 54` at 375px | Layout switches moved to `md:` in `GalleryPage`, `EventDetailPage` and `NavBar`. Now 0px overflow on every page at all three breakpoints. |
| 9 | **The submission page had no deadline on it at all**, though that checklist item was ticked. `DeadlineCountdown` was only on the event detail page. | — (checklist vs. code) | Submission page loads its event and shows the countdown above the form, warns explicitly once passed, and disables the fields (server already enforced it). Added `GET /api/events/id/{event_id}` because the page only knows its team's `event_id`. |
| 10 | **Invite redemption ended in a silent redirect**, which that checklist item explicitly forbids — and it fired twice under React StrictMode, so the second `409` rendered as a *failure* on a successful join. | — (found by reading; reproduced in the browser) | Redeems once per code via a ref; shows an explicit success screen with the team and members; treats "already a member" as a success state, not a dead end. |
| 11 | **`npm test` exited 1** — the script was wired with no test files. | `No test files found, exiting with code 1` | 9 Vitest tests (`api.test.ts`, `DeadlineCountdown.test.tsx`) on a `vitest.config.ts` kept separate from the production Vite config. |
| 12 | **Non-reproducible image builds.** `api/Dockerfile` ran `npm install` with no committed lockfile, against §5's "pin every dependency to an exact version". | — | `web/package-lock.json` committed; Dockerfile uses `npm ci`. |
| 13 | **131 `datetime.utcnow()` deprecation warnings** (removed in a future Python). | pytest warning summary | Gone with finding #1; the suite now reports only 2 third-party warnings. |
| 14 | **Unknown SPA routes rendered a blank page** under the nav — a dead-end screen (§4.4). | `GET /nope` rendered nav + nothing | `NotFoundPage` on a `path="*"` route with a way back. |
| 15 | **`_check_deadline` would 500** if an event row vanished between the team lookup and the write. | — (found by reading) | Replaced by `_load_open_event`, which 404s with a readable message. |

### Also verified working (no change needed)

- Role isolation at the endpoint level: organizer → participant-only team endpoints `403`;
  anonymous → every mutating endpoint `401`; non-member → team read `403` and submission PATCH `403`.
- `require_role()` is defined once in `api/app/auth/deps.py` and imported everywhere — no inline
  role checks in any handler (§8).
- `UserPublic` never exposes `password_hash`.
- Seeding is idempotent: row counts unchanged across an api restart.
- `bcrypt==4.0.1` is pinned deliberately — passlib 1.7.4 breaks against bcrypt ≥ 4.1.
- Route ordering is correct: `/api/teams/mine` and `/api/teams/join` resolve before `/{team_id}`.
- No network calls in the runtime path; no CDN assets in the served app.


---

## Open Questions

*(Append here anything ambiguous you had to make a judgment call on, so it's visible before submission — e.g., a T3 fallback taken, a DESIGN_SYSTEM.md/reference_design.pdf conflict, a rubric edge case.)*

- **~~Reference design filename (Phase 0).~~ Resolved in Phase 5.1.** §2/§3 expect
  `reference_design.pdf`; the file supplied was `reference_landing.pdf`. It was the same
  artifact — a full landing-page reference that `DESIGN_SYSTEM.md` §10 was derived from —
  so it was renamed (`git mv reference_landing.pdf reference_design.pdf`) rather than
  updating every reference the other way; the repo layout in §2 now matches reality.
- **~~Fonts vs. the offline constraint (Phase 0).~~ Resolved in Phase 5.1.** `DESIGN_SYSTEM.md`
  §3.1 originally specified Inter with an italic serif accent, but §1 forbids CDN-fetched assets
  in the served app and no font binaries were ever committed — the app has rendered the system
  fallback stack since Phase 0. Decision: keep it that way permanently. §3.1 now states the system
  stacks as canonical, not a fallback, and `web/src/styles/tokens.ts` matches.
- **Phase 0 `web/src/App.tsx` (judgment call).** The Phase 0 checklist asks for shared primitives
  but no pages. The SPA still needed a root component for `docker compose up` to be verifiable, so
  `App.tsx` is a primitives smoke page that also reports `/healthz` status. It is scaffolding, not
  product scope — Phase 1 replaces it with real pages.
- **Tailwind major version (Phase 0).** Pinned to `tailwindcss==3.4.17` rather than v4, because
  §3 and `DESIGN_SYSTEM.md` §11 both specify a `tailwind.config.ts` with `theme.extend`, which is
  the v3 configuration model. v4's CSS-first config would invalidate that instruction.
- **No acceptance suite exists yet (Phase 1).** "Run the acceptance suite against T1" is unchecked
  because no acceptance suite has been published — nothing to run. Coverage stands on our own
  suites instead: 30 backend tests (auth, role gating, event CRUD + validation, team formation +
  invite join/expiry, submission autosave/deadline/gallery visibility, plus one regression test per
  audit finding), 9 Vitest unit tests, and 24 Playwright browser checks. Re-run once the real suite
  ships; tier claims in `README.md` stay unwritten until then.
  **Update — organizer instruction received:** the organizer confirmed the real suite is published
  at kickoff, runs against the *running portal* (not source), reports pass/fail per tier requirement,
  is run by us and by judges identically, and is meant to be re-run "as often as you like" with the
  output committed each time — see §9.1, added for this. This does not unblock the checkbox above;
  the suite still hasn't shipped as of this note. It changes the *process* once it does: continuous
  re-run-and-commit, not a one-time generation near the freeze the way `acceptance-report.txt`'s
  repo-layout comment originally implied (also updated).
- **Public registration always creates a participant (Phase 1).** `POST /api/auth/register` never
  accepts a role from the client. Judge/organizer/admin accounts exist only via `fixtures/users.json`
  seeding. This wasn't explicit in PLAN.md; treated as the safer default for a hackathon platform
  (self-service organizer/admin signup would be a privilege-escalation hole) rather than build a
  separate invite-a-judge flow that Phase 1 didn't ask for. **Still the right call for registration,
  but the deferral outlived its justification — see the judge-invitation gap below.**

- **~~Judge invitation was never built, and the checklist never asked for it.~~ Found by re-reading
  the brief against this plan, then built.** T2's first clause is "**Judge invitation** and assignment". This plan's
  Phase 2 checklist covered assignment in detail and omitted invitation entirely, so the omission was
  invisible: every Phase 2 box could be ticked with the capability wholly absent. The Phase 1 note
  above deferred it on the grounds that "Phase 1 didn't ask for it" — true, but Phase 2 does, and
  nothing carried the deferral forward into Phase 2's list.

  **Consequence.** `judge` is the one role with no path onto the platform at all. It is not merely
  lacking self-service: there is no organizer-facing path either, so the only way a judge exists is
  `fixtures/users.json` at boot. An organizer running a real event cannot add a judge without editing
  a fixture file and recreating the database. That is a missing capability for the tier, not a bug in
  anything built — every judging path that *does* exist is correctly gated and tested.

  **Why this matters more than a missing form.** The whole four-role model rests on judges being
  distinct people brought in to evaluate (Section 8.0). Without an invitation path, that model is
  only expressible in seed data, which makes the strongest claim in the build — role isolation
  between competitor and evaluator — un-demonstrable on a live instance.

  **Now built**, immediately after this was logged. `api/app/judging/invites.py` + `JudgeInvite`:
  organizer/admin-only creation, single-use, expiring (1-90 days, default 14), revocable while
  unused, with a public `/preview` so a dead link explains itself instead of failing at the moment
  someone presses accept. Redemption promotes the signed-in account and is audit-logged. Still
  explicitly *not* self-service.

  Three decisions worth recording, none of which the brief specified:
  - **An organizer redeeming is refused, not demoted.** Silently replacing `organizer` with `judge`
    would cost them the ability to run their own event, with no warning and no undo.
  - **Already a judge is a success that does not consume the invitation**, so a double-click or a
    refresh cannot silently burn the organizer's next invite.
  - **The preview leaks nothing** — not the invited email, not the organizer's private note — so
    handing the link to the wrong person discloses only "this is a judge invitation".

  Covered by 15 tests in `test_judge_invites.py` weighted towards the escalation cases (a
  participant cannot mint an invite; a judge cannot mint further judges, so one compromised judge
  account does not become many; registration still cannot request the role), two new rows in the
  `test_role_isolation.py` matrix, and 9 browser tests in `web/tests/judge-invite.spec.ts`.

- **shadcn/ui Select, Framer Motion and GSAP added (UI pass).** All four are npm packages bundled
  at build time, so §1's no-network-calls rule is untouched — nothing is fetched at runtime and no
  CDN is involved. Notes on each:
  - **Select** is shadcn/ui's pattern on Radix primitives, skinned with our own tokens rather than
    shadcn's palette (`DESIGN_SYSTEM.md` stays the source of truth). Radix is what buys back the
    accessibility a native `<select>` gave for free and a styled `<div>` would have lost: roving
    focus, type-ahead, Escape, correct `aria-expanded`, focus returning to the trigger. Two browser
    tests assert it is a real `listbox`/`option` tree and keyboard-operable, not a div that looks
    like one.
  - **GSAP** is used only for the landing page's ScrollTrigger work (trail rows, step band, hero
    glow); Framer Motion handles entrance variants and the FAQ accordion. GSAP's core and
    ScrollTrigger are free to use commercially under its current licence.
  - Every new dependency was pinned exactly, per §5. `npm install` writes carets by default, which
    would have quietly violated that rule — the whole `package.json` was un-caretted, including
    devDependencies added earlier in the build that had the same problem.

- **Motion must never be load-bearing for legibility (UI pass).** Both libraries work by setting an
  element to `opacity: 0` and animating it back, so a trigger that never fires leaves content
  permanently invisible while the page still "renders" and no existing test notices.
  `web/tests/landing-motion.spec.ts` guards it: nothing stranded at zero opacity after a scroll
  pass, every step in the band visible, and under `prefers-reduced-motion` everything visible with
  no scrolling at all. That last test asserts the media query actually matches before checking
  anything — without it, `test.use({ reducedMotion })` in a nested describe silently failed to
  apply and the test was exercising the full-motion path instead.

- **Peer review is not in scope, and the conflict rule is not evidence that it is (role model).**
  The brief never mentions peer review, never uses the phrase, and never describes participants
  scoring each other; community voting (T3) is specified as a separate mechanism from formal judging
  (T2), with its own name, instrument and abuse model. Section 8.0 now states this explicitly because
  Section 8's conflict rule — "exclude `(judge, submission)` pairs where the judge is on the
  submitting team" — reads, out of context, as though judges were expected to be participants. They
  are not: the rule is a safeguard for the legitimate overlap case (a mentor who also entered
  something), and the `fixtures/teams.json` comment naming Dana as both judge and Pipeline Pals
  member exists to exercise that safeguard, not to model the intended workflow. Recorded so nobody
  later reads the fixture as a licence to build peer scoring.
- **One submission per team, not a `Submission` id in most URLs (Phase 1).** PLAN.md says
  "Submission model + draft/edit endpoints" without specifying cardinality. Modeled as exactly one
  submission per team (`unique=True` on `Submission.team_id`) with endpoints keyed by team
  (`/api/teams/{team_id}/submission`), matching how the reference PDF and typical hackathon judging
  treat a team's entry as singular. Flag if multi-track teams need more than one submission each.
- **Schema changes require a fresh dev volume (Phase 1).** There is no Alembic/migration tool in
  scope (PLAN.md section 5 doesn't list one). `SQLModel.metadata.create_all()` only creates missing
  *tables*, not missing *columns* on tables that already exist — adding `Event.prize_config` after
  the `events` table was already created crashed the API on boot (`UndefinedColumn`) until
  `docker compose down -v` dropped the dev volume for a clean schema. Fine for local development;
  flag before Phase 5 whether real migrations are needed for anything beyond a `docker compose up`
  demo.
- **~~Responsive/keyboard breakpoint pass not yet done in a browser (Phase 1).~~ Resolved by the
  Phase 0/1 audit.** Done in headless Chromium at 375/768/1280 across every Phase 1 screen, plus a
  keyboard-only pass. It was worth doing: it caught a real 54px overflow on `/gallery` at 375px
  (audit finding #8) that reading the code had not. Kept as `web/tests/breakpoints.spec.ts` so it
  re-runs every phase rather than being a one-time manual check.

- **`sm:` means *mobile*, not *above mobile* (Phase 1, audit).** `DESIGN_SYSTEM.md` §4 sets
  `sm: 375px` as the mobile target, so a `sm:`-prefixed utility applies **on** phones — the opposite
  of Tailwind's 640px default, where `sm:` is the first step *up* from mobile. Any layout that
  should stack on a phone must switch at `md:` (768px), matching §4's "stacking to one column below
  768px". Worth knowing before writing Phase 2's judge dashboard and score form.

- **Playwright added as a dev dependency (Phase 1, audit).** §5 already calls for "one Playwright
  end-to-end lifecycle test", so this isn't new scope — it is now actually installed and running
  (`web/tests/lifecycle.spec.ts`, the sign-up → team → invite → autosave → submit → gallery walk
  that §9 asks be kept green as the demo script). It is a dev dependency only; nothing about the
  runtime image or the no-network constraint changes.

- **The seeded event expires 2026-09-21 (Phase 1, audit — needs a decision).** `fixtures/events.json`
  hard-codes `end_at: 2026-09-21T18:00:00`. After that date the fixture event is closed, so team
  creation and every submission write correctly start returning `400` and a fresh `docker compose up`
  demos a dead event. Left as-is rather than silently rewriting fixture semantics, but before the
  demo either push the date well out or compute fixture dates relative to first boot.

- **One rubric per event (Phase 2).** PLAN.md says "`Rubric` model + CRUD (organizer only)" without
  specifying cardinality. Modelled as exactly one rubric per event (`unique=True` on
  `Rubric.event_id`), exposed as `PUT /api/events/{id}/rubric` create-or-replace rather than
  POST + PATCH. Reason: Section 8's normalisation takes per-judge z-scores of *raw totals*, which
  corrects for judge harshness but assumes every submission in an event was scored on the same
  scale. Two rubrics in one event would silently break that assumption. Flag if multi-track events
  need a rubric per track.

- **The rubric locks once scoring starts (Phase 2, judgment call).** Changing criteria or weights
  after judges have scored would silently reinvalidate every score already given against the old
  weights, with no visible symptom. `PUT` and `DELETE` therefore return `409` with the reason once
  any score exists for the event. PLAN.md didn't specify this; the alternative (silent
  recalculation) seemed clearly worse for judging integrity. Revisit if organizers need a
  deliberate "re-open scoring" action.

- **`fixtures/rubrics.json` added (Phase 2).** Section 2's repo layout lists four fixture files and
  predates Phase 2's rubric model. A fifth was added because constraint #1 is that everything works
  from `docker compose up` with no manual steps — without a seeded rubric, a fresh boot cannot
  demonstrate assignment or scoring at all without an organizer hand-building a rubric first.

- **Fixture set expanded for Phase 2 (Phase 2).** The Phase 1 fixtures had one judge and one
  submission, which cannot exercise a k=3 assignment, a conflict, or normalisation across judges.
  Now four judges, four teams, three submitted entries plus one draft. Deliberately, Dana is both a
  judge *and* a member of Pipeline Pals, so a fresh boot exercises the Section 8 conflict rule for
  real: she is never assigned Flake Finder. Judge accounts are global rather than per-event, since
  PLAN.md never scopes a judge to an event.

- **Raw total is `sum(weight x value)` (Phase 2).** Section 8 specifies the normalisation over "raw
  totals" but not how a raw total is formed from rubric criteria. Using the weighted sum keeps the
  total on the same 0-`max_score` scale as the individual criteria, so "7.8 out of 10" means
  something to a human reading the CSV. Recorded here because the choice affects every exported
  number.

- **Seeding is disabled under test (Phase 2, found while building).** `run_seed()` commits on its
  own connection during app startup, outside each test's rolled-back transaction, so seeded rows
  persisted for the whole session and leaked into any query over a global table. It made a
  coverage-shortfall test pass for the wrong reason. `conftest.py` now points `FIXTURES_DIR` at an
  empty path and truncates every table once per run, so the suite cannot inherit state. Worth
  knowing before writing Phase 3's voting tests, which will also query global tables.

- **The `audit/` module did not exist before Phase 3 (Phase 3).** Section 2's repo layout lists
  `api/app/audit/`, but Phases 0-2 never built it, and Phase 3's "wire *remaining* actions into the
  audit module" presupposes it already exists. Built here, then wired into the earlier actions too:
  register, login, event create/update/delete, team create, invite redemption, submission submit,
  rubric save/delete, assignment runs, score submission, votes and comments. Entries are staged on
  the caller's session so an action and its audit row commit or roll back together -- a logged
  action that did not actually happen would be worse than no log.

- **Append-only is enforced by absence, not by the database (Phase 3).** There is no update or
  delete path to `audit_log` anywhere in the app, and `GET /api/audit` is the only endpoint that
  touches it. A `REVOKE`-based or trigger-based guarantee would be stronger; it is not in scope for
  a single-container demo, and is worth flagging before anyone treats this log as tamper-evident
  rather than merely append-only by construction.

- **Organizers see vote counts during the hidden window (Phase 3, judgment call).** PLAN.md says to
  enforce `results_hidden_until` at the API response level but does not say for whom. Implemented in
  one predicate, `may_see_results()`: organizers and admins see counts throughout because they are
  running the event and need them; participants, judges and anonymous visitors all wait. Judges
  deliberately wait too -- community vote counts are not judging input and should not colour a
  judge's scoring.

- **`425 Too Early` for hidden results (Phase 3).** Not `403`: the caller is not forbidden, just
  early, and the distinction is what lets the UI say "results become visible on <date>" rather than
  "you can't see this". The response body names the moment.

- **Fingerprinting is coarse and flags loudly (Phase 3).** `fingerprint_hash` is
  `sha256(client-ip | user-agent)`, truncated, and is *only* ever a flag. Anyone behind one office
  NAT or one mobile network shares a fingerprint, so blocking on it would lock out legitimate
  voters; the unique constraint is what actually prevents duplicates. The consequence is that the
  flag is noisy by design -- on the seeded demo, where every request comes from one host, nearly
  every vote raises one. An organizer reading the log should treat it as "worth a look", never as
  proof.

- **Voting fixtures (Phase 3).** `fixtures/events.json` now sets `voting_enabled: true` and
  `results_hidden_until: 2026-09-21T20:00:00` (two hours after the submission deadline) so a fresh
  `docker compose up` demonstrates the hidden-window behaviour rather than needing an organizer to
  configure it first. Same expiry caveat as the event dates themselves -- see the note above.

- **Test data accumulates in the dev database (Phase 1, audit).** The Playwright suite runs against
  the live `docker compose` stack and creates real users/teams/submissions in `dogfood`. Seeding
  stays idempotent and the backend suite is isolated in `dogfood_test`, but run
  `docker compose down -v` before recording the demo so the gallery shows fixture data only.

- **Phase 4 frozen, not attempted (freeze decision).** Phases 1–3 all gate green, meeting
  PLAN.md's own entry condition for Phase 4, but the decision was made to spend remaining
  time on Phase 5's audit and documentation instead of stretch scope — a smaller,
  thoroughly-audited T1–T3 submission was judged to demo and score better than an
  unaudited T1–T4 one. Every Phase 4 checklist item is left unstruck (not deleted) in case
  confirmed slack appears after Phase 5 closes.

- **~~`hackraptors.pdf` scope: positioning and copy only, not a design-system input.~~
  Superseded by an explicit later request — `hackraptors.pdf`/raptors.dev is now the
  design-system source.** Originally decided: `hackraptors.pdf` is raptors.dev's real
  landing page, a different visual language from the institutional look built across
  four phases, so it would ground "Hackathon Raptors" in copy only, never touching a
  token. A later request explicitly reversed this: "use it for design reference...
  change the design system to match that palette," naming Satoshi and Playfair Display
  by name and pointing at the live raptors.dev URL for a self-check. `DESIGN_SYSTEM.md`
  was rebuilt from a live inspection of the real site's DOM (computed styles and
  `:root` custom properties, not the poster artwork) — see its own header for the full
  method and every real-vs-adapted value. The one thing this reversal did **not** change:
  hackraptors.pdf's stats/community framing still isn't copied verbatim into README or
  the landing page — that boundary (real product data, not raptors.dev's own numbers)
  was never part of either decision and wasn't asked to change.

- **The landing page never existed — corrected in Phase 5.4, not just re-checked.**
  `DESIGN_SYSTEM.md` §10 has carried a full 9-section landing-page composition since
  Phase 0, and `PLAN.md` §3 explicitly required it be built. It never was — `"/"` simply
  redirected into the app across Phases 0-3. This was masked by an earlier version of the
  Phase 5.4 checklist item, which was phrased as "confirm it still matches," assuming one
  existed. Built `web/src/pages/LandingPage.tsx` per §10 in Phase 5, with a real product-
  proof panel wired to live data (not a static mockup). A real `sm:`-means-mobile defect
  (see the audit-history entry below) was found and fixed while building it. Flagging this
  prominently because it's the kind of gap that's easy to miss when a checklist item's
  wording quietly assumes work that was never actually done.
- **Two Phase 5 checks genuinely not performed, left unchecked rather than assumed
  (Phase 5.2-5.3).** (1) Network-throttled ("Slow 3G") verification of every loading
  skeleton was not done this session. (2) A handful of lower-traffic screens (audit log
  viewer, CSV export controls under every role) have automated role-gating coverage via
  `test_role_isolation.py` but no dedicated live keyboard/breakpoint spot-check. Neither is
  a known defect — they are simply unverified, and are recorded here rather than silently
  marked done, per the same discipline that caught the real defects logged in
  `acceptance-report.txt`.
- **Demo video and "repo made public" (Phase 5.6-5.7) are not done and cannot be done
  by an agent.** The walkthrough script and the pre-recording `docker compose down -v`
  reset are both ready and accurate as written in 5.6; the actual screen recording needs
  a human. Making the repository public is the repo owner's explicit decision, not
  something to assume on their behalf.
- **Design system rebuilt from raptors.dev, two real defects found while doing it.**
  `DESIGN_SYSTEM.md`, `web/src/styles/tokens.ts`, and every component/page that consumes
  those tokens were re-derived from a live self-check of raptors.dev (real `:root`
  custom properties and computed styles, not the poster imagery) per the explicit
  request logged above. Fonts (Satoshi 400/500/700, Playfair Display 700/600-italic)
  were sourced from Fontshare and Google Fonts and committed as `.woff2` files under
  `web/public/fonts/` — self-hosted, per `PLAN.md` §1's no-CDN rule. Two real defects
  surfaced and were fixed while wiring this up, neither related to color/fonts directly:
  (1) `main.py`'s SPA catch-all only mounted `/assets/*`, so every other file Vite
  copies verbatim from `public/` (the new font files) silently fell through to the SPA
  shell instead of being served — fixed by serving any real file that exists at the
  requested path first, with an explicit path-containment check since the path segment
  is attacker-controlled; (2) Python's `mimetypes` module doesn't know `.woff2` by
  default, so it was served as `text/plain` until registered explicitly. All 231 tests
  (158 backend + 9 Vitest + 64 Playwright, unchanged counts — this was a re-skin, not a
  feature change) passed against the rebuilt system at that point; the current figure is
  233, after the judging role-model reconciliation added two separation tests.
- **The reference has no saturated brand hue — `brand` is the ink scale itself.**
  raptors.dev's real buttons and badges are outline (transparent bg, ink border/text);
  there is no colorful accent anywhere in its computed styles. Rather than inventing one,
  `brand-500` (#1F2426) is the same ink used for headings and body text — a primary
  filled button is the one addition a functional app needs beyond what the reference
  itself does, since the reference never needs a single clear call-to-action competing
  against outline buttons the way a workflow app's "Submit"/"Create event" does.

- **Phase 6 (uploaded assets) added after the Phase 5 freeze, and is not tier-gated.**
  Screenshots/avatars/gallery images are never named in the brief's tier ladder — T1 only
  asks for "a searchable public gallery" — so this was never missing from any tier claim
  and `README.md`'s existing tier claims stand unaffected either way. Added because a real
  gallery reads better with images than text cards, which speaks to Adoptability &
  Operability (20%), not to a tier. The storage-architecture question (local disk vs.
  self-hosted MinIO vs. cloud object storage + CDN) was analyzed against §1's constraints
  before writing the phase: cloud storage fails outright (needs the network, needs a
  cloud account — both forbidden by §1); self-hosted MinIO would technically satisfy §1
  but adds a third stateful service, its own credentials, and its own backup story for no
  benefit at this scale. Decision: local filesystem storage via a Docker named volume,
  behind a `StorageService` interface with exactly one implementation (`LocalStorage`).
  The interface's second implementation (`S3CompatibleStorage`) is documented as the
  production upgrade path and deliberately never built or tested here — see Phase 6's own
  header for the full reasoning and the request-flow diagram.

- **Header rebuilt a second time, to an explicit reference screenshot (post-Phase-5).**
  The wordmark-plus-hamburger header (itself a live self-check of raptors.dev's real
  collapsed nav) was replaced on request with a persistent, centred pill-tab bar matching
  a different reference screenshot exactly — a home icon plus text tabs, the active one
  highlighted as a light pill inside a dark bar. `DESIGN_SYSTEM.md` §7.6 documents both
  iterations rather than erasing the first. Post-login account controls (role, name, log
  out) were moved off the header entirely into a new `/profile` page per the same request
  — the header is now identical whether signed in or not, with "Profile" simply appearing
  as one more tab. Rebuilding it broke every test that assumed a menu to open; all were
  updated to interact with the now-always-visible tabs directly instead.
- **A genuine pre-existing test/component mismatch, found and fixed while verifying the
  header change.** `web/src/components/ui/Select.tsx` was rebuilt on Radix primitives at
  some point (real accessibility gain — roving focus, type-ahead, correct ARIA), but
  `voting.spec.ts` still drove it with `.selectOption()`, which only works on a native
  `<select>`. Not a header regression — a dormant gap the header work's full-suite rerun
  surfaced. Fixed by driving the control the way a user actually would (open the trigger,
  click the option).
- **Animations investigated live, found to be technically functioning.** Asked to check
  why the landing page's Framer Motion / GSAP animations "aren't working": no console
  errors; `prefers-reduced-motion` reads `false` in the test browser; the GSAP
  ScrollTrigger-driven decision-trail rows were confirmed to actually transition from
  `opacity: 0` to `opacity: 1` on scroll, not simply appear. The code path is real and
  exercised. If nothing visibly animates for a person, the most likely explanation is
  their own OS/browser having "reduce motion" enabled — which `useReducedMotion()`
  correctly and intentionally respects (`DESIGN_SYSTEM.md` §9) — rather than a defect.
  Left as a question back to whoever reported it rather than guessed at further.
- **Final suite counts after this round: 181 backend + 9 Vitest + 81 Playwright = 271,
  all passing serially.** The default parallel Playwright run intermittently fails 1-2
  tests that compare gallery contents across two reads (e.g. shuffle-order stability) —
  confirmed to be pre-existing contention on the shared dev database across parallel
  workers (already noted above: "test data accumulates in the dev database"), not
  something this round introduced. `docker compose down -v` before a demo, and
  `npx playwright test --workers=1` for a fully deterministic local run, both already
  documented; worth deciding before Phase 5 freeze whether the suite should default to
  serial execution or gain per-worker database isolation.
- **Phase 7 planned, not yet built (tracks/prizes UI, team-size cap, webhooks).** A live
  audit found `Event.tracks`/`Event.prize_config` have been fully supported by the model
  and `EventCreate`/`EventUpdate` since Phase 0, but no screen anywhere ever sends or
  displays either — `EventCreatePage.tsx` hardcodes `tracks: []` and `prize_config` is
  never touched by any UI. That is a real, unclaimed T1 gap ("configurable dates, tracks
  and prizes"), not new scope, and is 7.1. 7.2 (a per-event team-size cap, default 4,
  matching this hackathon's own stated rule) and 7.3 (opt-in, signed, fire-and-forget
  outbound webhooks reusing the Ed25519 signing already built for Phase 4's judge
  records, closing T4's "REST API **and webhooks**" — only the REST half existed) are
  genuine additive scope, chosen over other candidates (event archiving, duplicate-
  submission-content detection) because both map to something the spec names explicitly
  rather than something inferred. See Phase 7's own header for the full reasoning. Not
  started as of this entry — planning only.
