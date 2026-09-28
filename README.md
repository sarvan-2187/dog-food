# JudgeR — Judge Raptors

A self-contained hackathon operations platform: event creation, team formation, submission
drafting, judge assignment, weighted-and-normalized scoring, and public voting with
timed results reveal — for an organization like [Hackathon Raptors](https://raptors.dev)
running several branded events with a judged proof pipeline and public results, not a
single-event demo.

Built by Team CodeHawk against `PLAN.md`, the execution spec for this build.

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
| Participant | `jordan@example.com` (and 5 others) | `participant-pass1` (see fixture) |

Anyone can also register a new account from the app — public sign-up always creates a
`participant`; the other three roles exist only via the seed data (see PLAN.md's Open
Questions for why).

To reset to a clean, fixture-only state (e.g. before a demo):

```bash
docker compose down -v
docker compose up --build
```

## What's here

- **Event lifecycle** — organizer/admin create an event with configurable dates, tracks,
  and prize config.
- **Team formation** — a participant creates a team or joins one via a shareable invite
  link (server-side expiry, not just a UI hide).
- **Submissions** — one per team, autosaving as you type, with a visible
  "Saving… / Saved / Unsaved changes" indicator and a server-enforced deadline that's
  never a surprise (the countdown is always on the page).
- **Judging** — a deterministic, conflict-aware assignment algorithm; a weighted rubric
  that locks once scoring starts; per-judge z-score normalization so one harsh judge
  doesn't distort the ranking. See `JUDGING.md`.
- **Public gallery & voting** — one vote per person, rate-limited, with results held back
  until a configured reveal time so early counts can't sway the vote — enforced in the API
  response itself, not just hidden in the UI.
- **CSV export** — users, submissions, assignments, raw scores, normalized results, for
  every event, organizer/admin only.
- **Append-only audit log** — every consequential action, timestamped, organizer/admin
  readable, with no update or delete path from any endpoint.

Role-based access control is enforced at the endpoint level throughout — `require_role()`
is written once (`api/app/auth/deps.py`) and imported everywhere; there is no role check
that lives only in the frontend.

## Status

271 tests passing across three suites, run live against this exact stack (run the
Playwright suite serially with `--workers=1` for a deterministic count — see
PLAN.md's Open Questions on shared-dev-database contention across parallel workers):

| Suite | Command | Result |
|---|---|---|
| Backend | `docker compose exec api pytest tests/ -v` | 181 passed |
| Frontend unit | `cd web && npm test` | 9 passed |
| Browser E2E | `cd web && npx playwright test --workers=1` | 81 passed |

No official acceptance suite has been published for this build. `acceptance-report.txt`
is therefore self-issued from the suites above (see PLAN.md Phase 5.5) — replace it the
moment a real suite exists. Every number in this README and in that report comes from a
real run against the live stack; neither is hand-edited.

## Documentation

- **`PLAN.md`** — the execution spec this build follows, phase by phase, including every
  judgment call made along the way (`## Open Questions`).
- **`DESIGN_SYSTEM.md`** — the design tokens and component patterns the frontend is built
  from, derived from `reference_design.pdf`.
- **`ARCHITECTURE.md`** — system design and the modular-monolith rationale.
- **`DATA-MODEL.md`** — full schema, entity relationships, import/export paths.
- **`JUDGING.md`** — the assignment algorithm, the normalization math, and the role-
  isolation and integrity decisions behind them.

## Development

```bash
# Backend tests (needs the stack up)
docker compose exec api pytest tests/ -v

# Frontend unit tests
cd web && npm ci && npm test

# Browser end-to-end tests (needs the stack up)
cd web && npx playwright install --with-deps chromium
npx playwright test
```

## Tech stack

Python 3.12 · FastAPI · SQLModel (SQLAlchemy 2.0 + Pydantic) · PostgreSQL 16 · session
cookies signed with `itsdangerous`, passwords hashed with `passlib[bcrypt]` · React +
TypeScript + Vite · Tailwind CSS · pytest + httpx (backend) · Vitest (frontend unit) ·
Playwright (browser E2E). Every dependency is pinned to an exact version
(`api/requirements.txt`, `web/package.json` + `package-lock.json`); nothing in the runtime
image reaches the network beyond the standard package registries at build time.

## License

MIT — see `LICENSE`.
