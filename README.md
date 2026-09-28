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

The official DOGFOOD `fixtures.json` (repo root) is loaded as a third event,
`sample-hack-2026`: 8 tracks, 30 judges, 40 teams, 40 submissions and 123 scores, closed
at the fixture's `submissions_close` (2026-03-01), so it refuses new submissions. Every
account it creates (e.g. judge `tomas.varga@example.org`, participant `priya1@example.org`)
has the password `dogfood2026`. How the loader handles the fixture's awkward cases:

- **Duplicate submission.** `prj_41` is team `tm_07` submitting the same repo a second
  time. A team has one submission here, so it merges into `prj_07`. Where a judge scored
  both copies, only their first score is kept.
- **A judge who gave the same score to everything.** Kept as is. Normalisation gives that
  judge zero influence (`JUDGING.md`).
- **Unfinished batches, uneven review counts.** The fixture has scores but no
  assignments, so each score becomes one assignment. Projects end up with 2 to 5 reviews
  and nothing assumes a fixed number.

### Acceptance checker

`.dogfood.toml` points the DOGFOOD checker at this stack, and `acceptance-report.txt` is
what it printed:

```bash
docker compose down -v && docker compose up --build   # fresh volume: ids below are fixed
python run.py .dogfood.toml > acceptance-report.txt
```

The checker never logs in. It sends fixed cookies, which the API accepts because
`docker-compose.yml` sets `DEMO_SESSION_TOKENS`. The API prints the matching
`.dogfood.toml` values at boot. **On a real deployment, delete that line and change
`SESSION_SECRET`.** Anyone who has one of those tokens is signed in as that account.

Upgrading an existing install needs no reset: new columns are added at boot
(`db.add_missing_columns()`). To go back to a clean, fixture-only state anyway (e.g.
before a demo):

```bash
docker compose down -v
docker compose up --build
```

## Deploy it — live in minutes

HackFlow is one Docker image plus Postgres. No Node, Python, or database to install on the
host, no build step to run by hand, no migrations, no seed script. Anywhere that runs Docker
runs HackFlow.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/sarvan-2187/dog-food)

| Where | Cost (approx.) | Time to live | Keeps uploads & signing key | How |
|---|---|---|---|---|
| **Render** (free) | Free, no card | ~10 min | No: reset on restart | Click the button above, or **New → Blueprint** on this repo. `render.yaml` creates the site and database. |
| **Any VPS** (Hetzner, DigitalOcean, Vultr, Hostinger) | ~₹350–500 / $4–6 a month | ~5 min | Yes | Commands below |
| **Google Cloud / AWS / Azure VM** | Free-trial credit | ~5 min | Yes | Commands below |
| **Oracle Cloud Always Free** (ARM) | Free | ~5 min | Yes | Commands below. Images build for ARM as-is. |
| **Your own laptop + Cloudflare Tunnel** | Free, no account | ~2 min | Yes | `docker compose up`, then `cloudflared tunnel --url http://localhost:8000`. The link lives only while the laptop is on. |

**On any server with Docker:**

```bash
git clone https://github.com/sarvan-2187/dog-food.git && cd dog-food
docker compose up -d --build
```

The site answers on port 8000. For a public deployment, first:

- **Delete the `DEMO_SESSION_TOKENS` line** in `docker-compose.yml`. It grants fixed, passwordless sessions for the acceptance checker.
- Set a real `SESSION_SECRET` and change the Postgres password.
- Set `APP_BASE_URL` to your public address, and put HTTPS in front (Caddy or Cloudflare).
- Change the seeded account passwords.

**Pick a region near your users.** For the DOGFOOD judging panel, which is mostly US-based
with the rest in Europe, US East (Virginia / New York) gives the best latency overall.

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
  one vote per person, with the organizer choosing who votes (signed-in accounts, anyone who
  confirms an email, or anyone with the link), rate-limited, with results held back until a configured reveal time
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

## Known limits

- **No embeddable gallery widget.** Submission links open in a new tab and are never
  embedded, by design, so T4 is not claimed.
- **No eligibility review step.** An organizer can't mark a submission ineligible or
  disqualify it. Every submitted entry goes to judge assignment.
- **Community voting can be gamed with multiple accounts.** Voting needs a signed-in
  account and is rate-limited, but anyone can register, so one person with several email
  addresses can vote several times. See `THREAT-MODEL.md` entry 25.
- **No judging deadline.** Judges see the projects assigned to them but no due date.
  Organizers follow up by hand from the progress view, with reminder emails when email is
  on.

## Status

481 tests passing across three suites, run live against this exact stack:

| Suite | Command | Result |
|---|---|---|
| Backend | `docker compose exec api pytest tests/ -v` | 363 passed |
| Frontend unit | `cd web && npm test` | 9 passed |
| Browser E2E | `cd web && npx playwright test` | 109 passed, 1 skipped |

The skipped spec is the emailed password-reset flow. It needs the local test inbox, so
it runs only when the stack is started with `docker-compose.mail.yml` (see "Email"
above), and skips itself otherwise.

The browser suite changes the same database it reads. Against a fresh stack it passes in
full with Playwright's default parallel workers. After many runs on one volume, one or two
specs can time out; each passes on its own, and `--workers=1` or a fresh volume avoids it
(see PLAN.md's Open Questions).

`acceptance-report.txt` is the unedited output of the official DOGFOOD checker
(`run.py`): 7 of 7 checks pass, and T1 and T2 are verified. T3 is claimed too. The
organisers judge T3 and T4 by hand because `run.py` has no checks for them, so the
report's "claimed but not verified: T3" line is expected. T4 is not claimed, because the
embeddable gallery widget is missing (see Known limits). The earlier self-issued report, written
before the checker was published, is kept at `docs/self-test-report.txt`.

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
