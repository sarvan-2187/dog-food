# DATA-MODEL.md — Dogfood 2026

Schema documentation for the tables SQLModel creates from `api/app/*/models.py`. All
timestamps are `TIMESTAMP WITH TIME ZONE` (see `api/app/timeutil.py`'s `utcnow()`) so a
client's local offset never drifts against the server's enforcement of a deadline — this
was a real bug (audit finding #1 in PLAN.md) before it was fixed.

There is no migration tool in this build (see PLAN.md Open Questions). `SQLModel.metadata.
create_all()` only creates missing tables, not missing columns on tables that already
exist — a schema change means a fresh `docker compose down -v` in development.

## Entities

### `users` (`api/app/auth/models.py`)

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `email` | str, unique | |
| `name` | str | |
| `password_hash` | str | bcrypt via `passlib`; never leaves the server — `UserPublic` is the response shape |
| `role` | enum | `participant` \| `judge` \| `organizer` \| `admin`. Public registration always creates `participant`; the other three roles exist only via `fixtures/users.json` seeding |
| `created_at` | timestamptz | |

### `events` (`api/app/events/models.py`)

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `slug` | str, unique | URL-facing identifier |
| `name`, `description` | str | |
| `start_at`, `end_at` | timestamptz | `end_at` is the hard submission/team-formation deadline, enforced server-side on every write |
| `tracks` | JSON list[str] | |
| `prize_config` | JSON dict | Free-form; organizer-configurable |
| `voting_enabled` | bool | Gates the Phase 3 vote/comment endpoints |
| `results_hidden_until` | timestamptz, nullable | Gates who may see vote counts and standings — enforced in the API response itself, not just hidden in the UI |
| `created_by_id` | int, FK → `users.id` | Must be `organizer` or `admin` |
| `created_at` | timestamptz | |

### `teams` / `team_memberships` (`api/app/teams/models.py`)

One event has many teams; one team has many members via the join table.

| `teams` column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `event_id` | int, FK → `events.id` | |
| `name` | str | |
| `invite_code` | str, unique | `secrets.token_urlsafe(6)`, generated on team creation |
| `invite_code_expires_at` | timestamptz | Defaults to 30 days out; checked server-side on redemption, not just hidden in the UI |
| `created_at` | timestamptz | |

| `team_memberships` column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `team_id` | int, FK → `teams.id` | |
| `user_id` | int, FK → `users.id` | |
| `joined_at` | timestamptz | |

Unique constraint: `(team_id, user_id)` — a user can't join the same team twice.

### `submissions` (`api/app/submissions/models.py`)

**One submission per team**, not per user — see PLAN.md Open Questions for the rationale
(matches how a hackathon typically judges a team's single entry).

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `team_id` | int, FK → `teams.id`, **unique** | Enforces the one-per-team rule at the DB level |
| `event_id` | int, FK → `events.id` | Denormalized for query convenience |
| `title`, `description`, `track` | str | |
| `status` | enum | `draft` \| `submitted`. Only `submitted` rows appear in the public gallery |
| `created_at`, `updated_at` | timestamptz | `updated_at` bumps on every autosave `PATCH` |

### `rubrics` (`api/app/judging/models.py`)

**One rubric per event** — see PLAN.md Open Questions: normalization takes per-judge
z-scores of *raw totals*, which assumes every submission in an event was scored on the
same scale, so two rubrics in one event would silently break that assumption.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `event_id` | int, FK → `events.id`, **unique** | |
| `name` | str | |
| `criteria` | JSON list[dict] | Each item: `{key, label, weight, max_score}`. Weights must sum to 1.0, enforced on every write. The rubric **locks** (`PUT`/`DELETE` return `409`) once any score exists for the event — see JUDGING.md |
| `created_at`, `updated_at` | timestamptz | |

### `judge_assignments` (`api/app/judging/models.py`)

A judge's mandate to score one submission — the output of the assignment algorithm
(Section 8 of PLAN.md, `api/app/judging/assignment.py`).

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `event_id` | int, FK → `events.id` | |
| `submission_id` | int, FK → `submissions.id` | |
| `judge_id` | int, FK → `users.id` | |
| `created_at` | timestamptz | |

Unique constraint: `(submission_id, judge_id)` — makes re-running the assignment
idempotent and blocks double-assignment.

### `scores` (`api/app/scoring/models.py`)

At most one score per assignment — re-submitting **edits** rather than stacking
duplicates.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `assignment_id` | int, FK → `judge_assignments.id`, **unique** | |
| `submission_id`, `judge_id` | int, FK | Denormalized for query convenience |
| `values` | JSON dict | criterion key → raw value |
| `comment` | str | |
| `raw_total` | float | `sum(weight × value)` across criteria — see JUDGING.md for why this formula was chosen |
| `created_at`, `updated_at` | timestamptz | |

### `votes` / `comments` (`api/app/voting/models.py`)

| `votes` column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `event_id`, `submission_id`, `user_id` | int, FK | |
| `fingerprint_hash` | str | `sha256(client-ip \| user-agent)`, truncated — a **soft** flag only, never a block (see JUDGING.md) |
| `created_at` | timestamptz | |

Unique constraint: `(user_id, submission_id)` — the **hard** duplicate-vote guard;
enforced by catching the resulting `IntegrityError`, not a pre-`SELECT` a concurrent
request could race past.

| `comments` column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `event_id`, `submission_id`, `user_id` | int, FK | |
| `body` | str | |
| `created_at` | timestamptz | |

### `audit_log` (`api/app/audit/models.py`)

Append-only **by construction**, not by a database-level guarantee (no `REVOKE` or
trigger) — there is simply no update or delete path to this table anywhere in the app,
and `GET /api/audit` is the only endpoint that reads it. See JUDGING.md's role-isolation
section for who may read it.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `actor_id` | int, FK → `users.id`, nullable | Null for genuinely anonymous actions, recorded honestly rather than attributed to a fake user 0 |
| `actor_role` | str | |
| `action` | str, indexed | e.g. `"event.create"`, `"submission.submit"`, `"vote.cast"` |
| `entity_type`, `entity_id` | str, int nullable | What the action was about |
| `detail` | JSON dict | Action-specific payload |
| `created_at` | timestamptz | |

Audit entries are written on the **same session** as the action they describe, so an
action and its log entry commit or roll back together.

## Entity relationships

```
users ──< events (created_by)
users ──< team_memberships >── teams ──< events
users ──< submissions (via teams, one-to-one with team)
events ──< rubrics (one-to-one)
events ──< judge_assignments >── submissions
users (judges) ──< judge_assignments
judge_assignments ──< scores (one-to-one)
users ──< votes >── submissions
users ──< comments >── submissions
users ──< audit_log (nullable actor)
```

## Import / export paths

- **Fixture seeding** (`api/app/seed.py`): `fixtures/users.json` → `fixtures/events.json`
  → `fixtures/teams.json` → `fixtures/rubrics.json` → `fixtures/submissions.json`, in that
  order, since each step needs the previous step's generated ids. Every insert is guarded
  by a lookup on the row's natural key, so re-running on an already-seeded database is a
  no-op.
- **CSV export** (`api/app/scoring/router.py`, stdlib `csv` only): `users.csv`,
  `submissions.csv`, `assignments.csv`, `scores.csv`, `results.csv` per event, organizer/
  admin only (see `test_role_isolation.py`).
