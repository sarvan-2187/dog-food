# PLAN.md — Dogfood 2026 Build Plan (Claude Code Execution Spec)

**Team:** CodeHawk

> **Audience:** this file is written for an AI coding agent (Claude Code) executing this build, not for a human reading for context. It is the execution-ready companion to `dogfood-2026-implementation-plan-colorful.pdf`, which holds the full strategic rationale, trade-off discussion, and formulas. This file exists so you don't have to re-derive decisions — it tells you exactly what to build, in what order, with what files, and what "done" means at each gate. If you need the *why* behind a decision here, the PDF has it; don't re-litigate it, just build.
>
> This plan is organized as **six sequential phases (Phase 0 → Phase 5)**. Each phase has a functional checklist *and* a user-experience checklist — treat both as part of the same Definition of Done. A phase that passes the acceptance suite but ships confusing, unresponsive, or unstyled screens is not done; UX is not a separate pass bolted on later, it's a gate criterion at every phase.

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
- Four roles: `participant`, `judge`, `organizer`, `admin`. Every mutating and every sensitive-read endpoint must be gated by role at the endpoint level — never rely on frontend hiding alone.
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
├── acceptance-report.txt      # generated near the end, not hand-written
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
│   │   └── audit/             # append-only log writer + query helpers
│   └── tests/
│       ├── test_auth.py
│       ├── test_events.py
│       ├── test_teams.py
│       ├── test_submissions.py
│       ├── test_judging.py
│       ├── test_scoring.py
│       ├── test_voting.py
│       └── test_role_isolation.py   # the cross-cutting 403 matrix — see Phase 2
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

This is the single biggest lever for making the platform feel like something Hackathon Raptors could actually run for real events, not a demo. Every phase's checklist below references back to this section — treat these as standing requirements, checked at every gate, not a one-time task.

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

### Functional checklist
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

**Gate status:** green apart from the unpublished acceptance suite. Verification standing:

| Suite | Command | Result |
|---|---|---|
| Backend | `docker compose exec api pytest tests/ -v` | 124 passed |
| Frontend unit | `cd web && npm test` | 9 passed |
| Browser E2E | `cd web && npx playwright test` | 45 passed |

Verified live against the seeded stack on a clean `docker compose up -d --build`: assignment produced 9 pairs
across 3 submissions with **zero** conflicts (Dana, who is both a judge and a Pipeline Pals member, was never
assigned Flake Finder); four judges of differing harshness scored; the normalised standings re-ranked against the
raw mean as intended. One defect was found and fixed in this phase: the standings table's `<th>` elements had no
`scope`, so the browser exposed them as generic cells and a screen reader reading a value never said which column
it came from.

---

## Phase 3 — Public (T3)

### Functional checklist
- [ ] `Event.voting_enabled` toggle + `Vote` model with unique constraint `(user_id, submission_id)`
- [ ] `Event.results_hidden_until` + enforce hiding at the **API response** level — test that the raw endpoint returns no score/vote data during the hidden window, not just that the UI hides it
- [ ] Randomized project ordering, seeded per-session
- [ ] `Comment` model + endpoints
- [ ] Rate limiting on vote/comment endpoints (in-process token bucket, no external service)
- [ ] Duplicate-vote detection: unique constraint as the hard guard, `fingerprint_hash` column flags (doesn't silently block) suspicious repeats
- [ ] Wire remaining actions into the `audit` module
- [ ] `api/tests/test_voting.py` passing
- [ ] **If time is tight:** fall back to the smaller "community interest" thumbs-up variant (PDF Section 9) rather than leaving full voting half-built — log this in `## Open Questions`
- [ ] Run the acceptance suite against T3

### UX checklist
- [ ] Voting UI clearly communicates *why* results are hidden during the voting window (e.g., "Results are hidden until voting closes on [date]") rather than just disabling a control with no explanation
- [ ] Voting/comment rate limiting shows a clear, friendly message when a limit is hit ("You've reached the voting limit for now — try again shortly"), not a raw 429
- [ ] Comment submission: inline validation, optimistic append with rollback-on-failure, visible pending/sent state
- [ ] Randomized ordering doesn't cause layout jank on repeated visits within the same session (stable shuffle per session, as specified)
- [ ] All Phase 3 screens verified at mobile/tablet/desktop breakpoints and via keyboard-only navigation

**Definition of Done — Phase 3 gate:** acceptance suite reports T3 checks green (full scope or the documented fallback scope), and the Phase 3 UX checklist is fully checked.

---

## Phase 4 — Stretch (T4) and bonus challenges

Only enter this phase if Phases 1–3 gates are all green with real time remaining.

### T4 functional checklist
- [ ] REST API/OpenAPI completeness audit: confirm every UI action has a documented endpoint (check invite-link redemption and any other click-triggered-DB-write paths specifically)
- [ ] Certificate/record generation (server-side HTML-to-PDF or a PDF-generation library — no external service)
- [ ] Bulk import/export (full event JSON export/import)
- [ ] Signed judge participation records (local ed25519 keypair via `cryptography`, entirely offline)
- [ ] Embeddable gallery widget (lowest priority — cut first if time runs short)

### Bonus challenges, in this order
- [ ] Normalization Proof: present the raw-vs-normalized ranking table on fixture data
- [ ] Threat Model write-up: pair each attack with the mitigation already built in Phases 2–3
- [ ] API First: only after the OpenAPI completeness audit above passes
- [ ] Pairwise Mode / Bradley-Terry: only with 10+ hours of confirmed slack and a validated worked example

### UX checklist (if any T4 work touches the UI)
- [ ] Certificate download/generation shows a clear loading + success state
- [ ] Bulk import/export shows progress and a clear success/failure summary, not a silent file drop
- [ ] Any new screen still meets the full Section 4 bar — T4 is not an excuse to skip loading/empty/error states

---

## Phase 5 — Polish, UX Audit & Freeze Prep

This phase exists specifically so UX quality gets one dedicated, whole-app pass rather than only being checked screen-by-screen as you go. Do not skip it even if Phases 1–3 individually passed their UX checklists.

- [ ] Full click-through of every screen in the app, on all three breakpoints, as each of the four roles — note and fix any inconsistency in spacing, color, or component usage against `DESIGN_SYSTEM.md`
- [ ] Full keyboard-only pass: tab through every screen, confirm every action is reachable and focus states are visible
- [ ] Confirm every loading/empty/error state actually appears when triggered (simulate empty DB sections, slow network via devtools throttling, and a forced 500 to check the error path) — don't just trust that the component exists, verify it renders
- [ ] Landing page matches `reference_design.pdf` (if supplied) — if not yet supplied, confirm it is at least clean, responsive, and consistent with Tailwind defaults
- [ ] Run the full acceptance suite one final time; save output verbatim to `acceptance-report.txt` at repo root; fix only what it flags from this point on
- [ ] Record the 5-minute demo video from the rehearsed Playwright lifecycle path
- [ ] Finalize `README.md`, `ARCHITECTURE.md`, `DATA-MODEL.md`, `JUDGING.md` (see Section 10)

**Definition of Done — Phase 5 / submission gate:** acceptance report committed, all four docs complete and cross-checked against it, demo video recorded, repo made public, license in place.

---

## 8. Judging integrity — implement exactly this

**Assignment algorithm** (implement as `assign_judges(submissions, judges, team_memberships, k) -> list[JudgeAssignment]`):

1. Build a conflict set: exclude `(judge, submission)` pairs where the judge is on the submitting team.
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

- **Reference design filename (Phase 0).** §2/§3 expect `reference_design.pdf`; the file supplied is
  `reference_landing.pdf`. Treated as the same artifact — it is a full landing-page reference, and
  `DESIGN_SYSTEM.md` §10 was derived from it. Rename one or the other before submission so the
  repo layout in §2 matches reality.
- **Fonts vs. the offline constraint (Phase 0).** `DESIGN_SYSTEM.md` §3.1 specifies Inter with an
  italic serif accent, but §1 forbids CDN-fetched assets in the served app. No font binaries are
  committed, so the app currently renders the system fallback stack declared in
  `web/src/styles/tokens.ts`. Decision needed: commit self-hosted `.woff2` files under
  `web/public/fonts/`, or accept the system stack permanently and simplify §3.1.
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
- **Public registration always creates a participant (Phase 1).** `POST /api/auth/register` never
  accepts a role from the client. Judge/organizer/admin accounts exist only via `fixtures/users.json`
  seeding. This wasn't explicit in PLAN.md; treated as the safer default for a hackathon platform
  (self-service organizer/admin signup would be a privilege-escalation hole) rather than build a
  separate invite-a-judge flow that Phase 1 didn't ask for.
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

- **Test data accumulates in the dev database (Phase 1, audit).** The Playwright suite runs against
  the live `docker compose` stack and creates real users/teams/submissions in `dogfood`. Seeding
  stays idempotent and the backend suite is isolated in `dogfood_test`, but run
  `docker compose down -v` before recording the demo so the gallery shows fixture data only.
