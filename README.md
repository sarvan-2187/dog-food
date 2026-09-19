# HackFlow

[![License: MIT](https://img.shields.io/badge/license-MIT-3ddc84?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-467%20passing-3ddc84?style=flat-square)](acceptance-report.txt)
[![Python](https://img.shields.io/badge/python-3.12-1F2426?style=flat-square&logo=python&logoColor=white)](api/requirements.txt)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-1F2426?style=flat-square&logo=fastapi&logoColor=white)](api/requirements.txt)
[![React](https://img.shields.io/badge/React-18-1F2426?style=flat-square&logo=react&logoColor=white)](web/package.json)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-1F2426?style=flat-square&logo=typescript&logoColor=white)](web/package.json)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-1F2426?style=flat-square&logo=postgresql&logoColor=white)](docker-compose.yml)
[![Docker Compose](https://img.shields.io/badge/docker%20compose-up-1F2426?style=flat-square&logo=docker&logoColor=white)](docker-compose.yml)

A self-contained hackathon operations platform: event creation, team formation, submission
drafting, judge assignment, weighted-and-normalized scoring, and public voting with
timed results reveal — for an organization like [Hackathon Raptors](https://raptors.dev)
running several branded events with a judged proof pipeline and public results, not a
single-event demo.

Built by Team CodeHawk against `PLAN.md`, the execution spec for this build.

## Screenshots

All captured live against the running `docker compose` stack on fixture-only data —
none of these are mockups.

| | |
|---|---|
| **Landing** — RiskSentinel-style hero, raptors.dev's own gradient palette | **Public gallery** — voting, comments, results held back until reveal |
| [![Landing page](docs/screenshots/landing-hero.png)](docs/screenshots/landing-hero.png) | [![Gallery](docs/screenshots/gallery.png)](docs/screenshots/gallery.png) |
| **Judging rubric** — weighted criteria, live "weights add up to 1.00" check | **Event control** — assignment, rubric lock, voting/reveal controls |
| [![Rubric builder](docs/screenshots/rubric-builder.png)](docs/screenshots/rubric-builder.png) | [![Results/event control](docs/screenshots/results.png)](docs/screenshots/results.png) |

## Quickstart

```bash
docker compose up
```

That's it — no `.env` to fill in, no separate seed script, no manual migration step. The
API creates its schema and seeds fixture data automatically on first boot. Open
`http://localhost:8000`.

Seeded accounts (see `fixtures/users.json`) — password is the value shown:

| Role | Email | Password |
|---|---|---|
| Organizer | `alice@example.com` | `organizer-pass1` |
| Admin | `priya@example.com` | `admin-pass123` |
| Judge | `sam@example.com` (and `mina@`, `omar@`, `dana@`) | `judge-pass123` (see fixture for the others) |
| Participant | `jordan@example.com` (and 6 others) | `participant-pass1` (see fixture) |

Anyone can also register a new account from the app. Public sign-up always creates a
`participant`. Judges join by an event's invitation link, and organizers by an admin's
invitation link or an admin changing their role on **Users**. Admins exist only in the seed
data (see PLAN.md's Open Questions for why).

Two seeded events are worth knowing for a demo:

| Event | State | Use it to show |
|---|---|---|
| `dogfood-2026` — HackFlow Hackathon 2026 | Open for submissions | Teams, submissions, project links, announcements, voting |
| `judging-showcase-2026` — Raptor Judging Showcase | Submissions closed, results hidden | Judge assignment, scoring, judging progress, conflicts, winners |

Judging opens only once an event's submissions close, which is why the second one exists.

Upgrading an existing install needs no reset: new columns are added at boot
(`db.add_missing_columns()`). To go back to a clean, fixture-only state anyway (e.g.
before a demo):

```bash
docker compose down -v
docker compose up --build
```

## Email (optional) — self-service password resets

Out of the box HackFlow sends no email and makes **zero** outbound network calls. Anyone who
forgets their password gets a one-time reset link from an organizer (**Dashboard → Help
someone sign in**).

Point it at your own mail server and resets become fully self-service: **Forgot password?**
on the login page emails a link that works once and expires in 30 minutes. It uses plain
SMTP via Python's standard library — no email SDK, no hosted service.

**Try it locally, with no internet:** a bundled test inbox catches every email.

```bash
docker compose -f docker-compose.yml -f docker-compose.mail.yml up
```

The app runs at `http://localhost:8000` as usual. Emails appear at **`http://localhost:8025`**.

**Real delivery:** copy `.env.example` to `.env` (git ignores it), fill it in, then
`docker compose up -d api`.

| Setting | Gmail / Workspace | Outlook / Microsoft 365 |
|---|---|---|
| `SMTP_HOST` | `smtp.gmail.com` | `smtp.office365.com` |
| `SMTP_PORT` | `587` | `587` |
| `SMTP_SECURITY` | `starttls` | `starttls` |
| `SMTP_USERNAME` | your address | your address |
| `SMTP_PASSWORD` | an *app password* (needs 2-step verification) | an *app password* |
| `SMTP_FROM` | `HackFlow <you@your-domain>` | same |
| `APP_BASE_URL` | the URL people use to reach HackFlow (default `http://localhost:8000`) | same |

Then sign in as an admin and press **Send test email** on the dashboard's **Email delivery**
card — it reports the mail server's answer in plain language. Delivery itself is up to your
provider: a brand-new sending address can land in spam until the domain has SPF/DKIM set up.

**Locked-out admin?** `docker compose exec api python -m app.auth.reset_link you@example.com`
prints a one-time reset link for any account.

## What's here

- **Event lifecycle** — new events start as **drafts** only organizers can see, and go
  public with **Publish**. Dates, rules, tracks, prizes and team-size cap are all editable
  from Event settings, including **Close submissions now**. Every event shows its phase
  (Upcoming / Open / Judging / Results) and a countdown worded for it.
- **Multi-event judging** — each event has its own judge panel. Judges are invited *to an
  event*, and assignment only ever draws from that event's panel. Judging opens when
  submissions close, so nobody scores a project its team can still change.
- **Judging progress** — "X of Y scores in", each judge's progress (furthest behind
  first), removing a judge who dropped out (their scores stay; their unscored work is
  re-assigned), email reminders, and judges can declare a conflict of interest.
- **Winners** — each configured prize is awarded to a project, suggested from the
  standings and confirmed by the organizer. Winners appear on the event page and
  certificates at the results reveal.
- **Announcements** — organizers post updates to everyone in an event. They appear on the
  event page and participants' dashboards, can be emailed, and are sent to the event's
  webhooks.
- **Team management** — one team per person per event; members can leave; the captain
  renames the team, removes members, hands over captaincy and replaces the invite link.
- **Project links** — code, live demo and video links on every submission, validated
  (http/https only), shown to judges and in the gallery. Linked, never embedded.
- **Admin users** — search accounts, change roles, deactivate, and invite organizers by
  link. The admin role is never granted from the UI.
- **Sign-in protection** — failed logins are limited per account and per IP, and checked
  before the password, so a correct guess made after the limit is still refused.
  Responses take the same time whether or not the account exists.
- **Account recovery** — "Forgot password?" emails a single-use reset link when email is
  set up. Otherwise organizers issue one from their dashboard, and a server command
  covers a locked-out admin. Any password change signs the account out everywhere.
  Profile has **Change password** and name editing.
- **Team formation** — a participant creates a team or joins one via a shareable invite
  link (server-side expiry, not just a UI hide), capped at a per-event max team size
  (default 4, matching Dogfood's own rule) enforced server-side.
- **Submissions** — one per team, autosaving as you type, with a visible
  "Saving… / Saved / Unsaved changes" indicator and a server-enforced deadline that's
  never a surprise (the countdown is always on the page).
- **Judging** — a deterministic, conflict-aware assignment algorithm; an event can hold
  several weighted rubrics (e.g. Technical + Presentation), combined into one score form
  and locked once scoring starts; per-judge z-score normalization so one harsh judge
  doesn't distort the ranking. See `JUDGING.md`.
- **Public gallery & voting** — scoped per hackathon (pick an event, then see its gallery),
  one vote per person, rate-limited, with results held back until a configured reveal time
  so early counts can't sway the vote — enforced in the API response itself, not just
  hidden in the UI.
- **Uploaded images** — submission screenshots and profile avatars, stored on local disk
  behind a swappable `StorageService` interface — no cloud account or CDN, works fully
  offline. See `ARCHITECTURE.md`.
- **CSV export** — users, submissions (with their project links), assignments, raw
  scores, normalized results, for every event, organizer/admin only.
- **Append-only audit log** — every consequential action, timestamped, organizer/admin
  readable, with no update or delete path from any endpoint.
- **Certificates & signed records** — server-rendered participation certificates (PDF, no
  external service) that name any prize won, and judge participation records signed with a local Ed25519 key,
  verifiable offline against `GET /api/public-key` without trusting the server again.
- **Bulk event export/import** — an event's config (including rules), rubric, teams and
  submissions (including links) as one JSON file, for backup or migration between
  environments. An import arrives as a draft, and its links are validated like any other.
- **Guided onboarding** — a role-aware tour (driver.js, bundled — no network calls) starts
  once on first login and is replayable from `/profile`, so a fresh cohort of participants
  and judges can be pointed at the site rather than at a support doc. See `USER-MANUAL.md`.
- **Outbound webhooks** — organizers opt an event into signed HTTP callbacks
  (`submission.submitted`, `assignments.run`, `score.submitted`,
  `event.results_revealed`, `announcement.posted`), each payload signed with the same Ed25519 key used for judge
  participation records, so a receiver can verify it without trusting the network.

Role-based access control is enforced at the endpoint level throughout — `require_role()`
is written once (`api/app/auth/deps.py`) and imported everywhere; there is no role check
that lives only in the frontend.

## Status

467 tests passing across three suites, run live against this exact stack:

| Suite | Command | Result |
|---|---|---|
| Backend | `docker compose exec api pytest tests/ -v` | 349 passed |
| Frontend unit | `cd web && npm test` | 9 passed |
| Browser E2E | `cd web && npx playwright test` | 109 passed, 1 skipped |

The skipped spec is the emailed password-reset flow. It needs the local test inbox, so
it runs only when the stack is started with `docker-compose.mail.yml` (see "Email"
above), and skips itself otherwise.

The browser suite changes the same database it reads. Against a fresh stack it passes in
full with Playwright's default parallel workers. After many runs on one volume, one or two
specs can time out; each passes on its own, and `--workers=1` or a fresh volume avoids it
(see PLAN.md's Open Questions).

No official acceptance suite has been published for this build. `acceptance-report.txt`
is therefore self-issued from the suites above (see PLAN.md Phase 5.5) — replace it the
moment a real suite exists. Every number in this README and in that report comes from a
real run against the live stack; neither is hand-edited.

## Documentation

- **`USER-MANUAL.md`** — illustrated, step-by-step guide for participants, judges, and
  organizers, in plain language. Start here if you want to *use* HackFlow rather than
  modify it.
- **`PLAN.md`** — the execution spec this build follows, phase by phase, including every
  judgment call made along the way (`## Open Questions`).
- **`DESIGN_SYSTEM.md`** — the design tokens and component patterns the frontend is built
  from, derived from `reference_design.pdf`.
- **`ARCHITECTURE.md`** — system design and the modular-monolith rationale.
- **`DATA-MODEL.md`** — full schema, entity relationships, import/export paths.
- **`JUDGING.md`** — the assignment algorithm, the normalization math, and the role-
  isolation and integrity decisions behind them.
- **`THREAT-MODEL.md`** — twenty-four attacks, each paired with the mitigation already
  built and the file that enforces it.
- **`CREDITS.md`** — who made the bundled photographs and under which licence, plus the
  third-party software the stack runs.

## Development

```bash
# Backend tests (needs the stack up)
docker compose exec api pytest tests/ -v

# Frontend unit tests
cd web && npm ci && npm test

# Browser end-to-end tests (needs the stack up)
cd web && npx playwright install --with-deps chromium
npx playwright test

# ...including the emailed password-reset flow, against the local test inbox
docker compose -f docker-compose.yml -f docker-compose.mail.yml up -d
npx playwright test recovery.spec.ts
```

## Tech stack

Python 3.12 · FastAPI · SQLModel (SQLAlchemy 2.0 + Pydantic) · PostgreSQL 16 · session
cookies signed with `itsdangerous`, passwords hashed with `passlib[bcrypt]` · React +
TypeScript + Vite · Tailwind CSS · driver.js (guided tour, bundled) · optional email over
Python's standard-library `smtplib` · pytest + httpx (backend) · Vitest (frontend unit) ·
Playwright (browser E2E). Every dependency is pinned to an exact version
(`api/requirements.txt`, `web/package.json` + `package-lock.json`); nothing in the runtime
image reaches the network beyond the standard package registries at build time.

## License

MIT — see `LICENSE`.
