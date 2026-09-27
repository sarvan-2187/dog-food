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

- [ ] `git init` (only after kickoff — no code before the official start)
- [ ] Scaffold `docker-compose.yml` with `db` and `api` services
- [ ] `api`'s Dockerfile is multi-stage: stage 1 builds the Vite frontend (`node:20-slim`), stage 2 is `python:3.12-slim` copying the built frontend's static output into the image alongside the FastAPI app
- [ ] `api/app/db.py` (engine + session dependency) and `api/app/seed.py` (reads `fixtures/*.json`, idempotency-checked, called on app startup)
- [ ] Shared UI scaffolding: `web/src/components/ui/` (Button, Input, Card, Badge) and `web/src/components/feedback/` (Toast, Skeleton, EmptyState, ErrorState) built as reusable primitives *before* any feature page — every later screen consumes these rather than reinventing loading/error/empty markup per page

**Definition of Done — Phase 0 gate:** `docker compose up` boots both containers healthy with empty schema, on a clean checkout (clear local Docker build cache and retry if unsure). Do not proceed to Phase 1 until this works.

---

## Phase 1 — Core (T1)

### Functional checklist
- [ ] `User` model + `passlib` password hashing + session-cookie auth (`api/app/auth/`)
- [ ] Role enum (`participant`, `judge`, `organizer`, `admin`) + `require_role(*roles)` FastAPI dependency — apply to every mutating/sensitive endpoint from this point forward
- [ ] `Event` model + CRUD endpoints (organizer/admin only) — configurable dates, tracks, prize config
- [ ] `Team` model + `TeamMembership` join table + invite-link generation/redemption (server-side expiry check, not just UI hide)
- [ ] `Submission` model + draft/edit endpoints + autosave-friendly PATCH semantics
- [ ] Deadline enforcement: reject writes server-side once `Event.end_at` has passed — test by calling the endpoint directly post-deadline
- [ ] Public gallery endpoint with search (simple `ILIKE` on title/description)
- [ ] `api/tests/test_auth.py`, `test_events.py`, `test_teams.py`, `test_submissions.py` passing
- [ ] Run the acceptance suite against T1

### UX checklist (see Section 4 for detail)
- [ ] Event creation form: inline validation, clear field-level errors, disabled submit while saving
- [ ] Team formation: invite-link copy button with a "Copied" confirmation; joining flow shows a clear success/failure state, not a silent redirect
- [ ] Submission draft/edit: visible autosave indicator ("Saving… / Saved / Unsaved changes"); never loses entered content on a validation error
- [ ] Public gallery: loading skeleton while fetching, empty state with role-appropriate call-to-action, search with no-results state that's distinct from the empty-gallery state
- [ ] Deadline countdown or clear deadline display on the submission page — the user should never discover a deadline passed only via a rejected save
- [ ] All Phase 1 screens verified at mobile/tablet/desktop breakpoints and via keyboard-only navigation
- [ ] Role-aware navigation: nav only shows links the current role can use

**Definition of Done — Phase 1 gate:** acceptance suite reports all T1 checks green, and every item in the Phase 1 UX checklist is checked. Do not start Phase 2 otherwise.

---

## Phase 2 — Judging (T2)

### Functional checklist
- [ ] `Rubric` model + CRUD (organizer only) — validate criteria weights sum to 1.0 on save, reject otherwise
- [ ] `JudgeAssignment` model + the assignment algorithm (Section 8) — implement as a pure, testable function separate from the endpoint handler
- [ ] `Score` model + score submission endpoint, restricted to the assigned judge for that specific assignment only
- [ ] Role isolation: judges cannot see other judges' scores; participants cannot see any score detail; organizers cannot submit a score by calling a judge endpoint directly
- [ ] Judge progress dashboard endpoint + frontend
- [ ] Normalization pipeline (Section 8) — pure function, unit-testable independent of the DB
- [ ] CSV export endpoints: users, submissions, assignments, raw scores, normalized results
- [ ] `api/tests/test_judging.py`, `test_scoring.py` passing
- [ ] `api/tests/test_role_isolation.py`: assert 403 for every role that shouldn't be allowed, for every mutating/sensitive endpoint so far
- [ ] Run the acceptance suite against T2

### UX checklist
- [ ] Judge progress dashboard leads with "X of Y assignments completed" prominently, not buried in a table; shows which specific submissions are still pending
- [ ] Score submission form: rubric criteria are clearly labeled with their weights, running total updates live as the judge fills it in, inline validation prevents an incomplete or out-of-range submission before the judge hits submit
- [ ] Clear, reassuring confirmation after score submission (not just a redirect) — the judge should know unambiguously that it saved
- [ ] Organizer rubric builder: validation error if weights don't sum to 1.0, shown inline at the field level, not as a generic form-level rejection
- [ ] CSV export buttons show a loading state for larger exports and a clear success (download starts) signal
- [ ] All Phase 2 screens verified at mobile/tablet/desktop breakpoints and via keyboard-only navigation

**Definition of Done — Phase 2 gate:** acceptance suite reports all T2 checks green, `test_role_isolation.py` has at least one negative-role test per mutating endpoint, and the Phase 2 UX checklist is fully checked. Do not start Phase 3 otherwise.

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

## Open Questions

*(Append here anything ambiguous you had to make a judgment call on, so it's visible before submission — e.g., a T3 fallback taken, a DESIGN_SYSTEM.md/reference_design.pdf conflict, a rubric edge case.)*
