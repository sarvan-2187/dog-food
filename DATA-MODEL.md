# DATA-MODEL.md — HackFlow

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
| `avatar_url` | str, nullable | Set via the `stored_files` upload flow below; `null` until the user uploads one |
| `created_at` | timestamptz | |
| `session_version` | int, default 0 | Signed into every session cookie; incremented on each password change or reset, which invalidates every older cookie at once (PLAN.md Phase 9.1). Added to existing volumes at boot by `db.add_missing_columns()` |

### `password_resets` (`api/app/auth/models.py`)

One row per reset link, whichever way it was issued (PLAN.md Phase 9).

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `user_id` | int, FK → `users.id` | The account the link resets |
| `token_hash` | str, unique | SHA-256 hex of the token. The raw token exists only in the email, the organizer's one-time response, or the CLI's output — never in the database |
| `channel` | enum | `email` (self-service, 30 min) \| `organizer` (hand-delivered, 60 min) \| `cli` (break-glass, 60 min) |
| `issued_by_id` | int, FK → `users.id`, nullable | The organizer/admin who issued it; `null` for `email` and `cli` |
| `created_at`, `expires_at` | timestamptz | Issuing a new link sets any earlier unused link's `expires_at` to now |
| `used_at` | timestamptz, nullable | Set on redeem; a link with `used_at` set is dead. Previewing a link never sets it |

### `events` (`api/app/events/models.py`)

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `slug` | str, unique | URL-facing identifier |
| `name`, `description` | str | |
| `start_at`, `end_at` | timestamptz | `end_at` is the hard submission/team-formation deadline, enforced server-side on every write |
| `tracks` | JSON list[str] | |
| `prize_config` | JSON dict | Shape: `{"prizes": [{"rank": "1st Place", "reward": "$500"}, ...]}`. A product convention, not a schema constraint — the column is a free-form `JSON` and nothing validates the inner shape server-side, so this is documented here rather than in a migration (PLAN.md Phase 7.1) |
| `max_team_size` | int | Default `4`, matching the hackathon's own "Team Size: 1–4" rule; enforced server-side in `teams/router.py`'s `join_team` (PLAN.md Phase 7.2) |
| `voting_enabled` | bool | Gates the Phase 3 vote/comment endpoints |
| `results_hidden_until` | timestamptz, nullable | Gates who may see vote counts and standings — enforced in the API response itself, not just hidden in the UI |
| `results_revealed_notified` | bool | One-shot guard so the `event.results_revealed` webhook topic fires exactly once, flipped the first time `public_results` is read after `results_are_public()` goes true (PLAN.md Phase 7.3) |
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

**An event holds a *set* of named rubrics** (e.g. "Technical" + "Presentation"), combined
into one flat criteria list at scoring time — not the one-rubric-per-event model this
table used earlier. Normalization still takes per-judge z-scores of *raw totals*, which
assumes every submission in an event was scored on the same combined scale, so the
weight-sum-to-1.0 check is enforced across the **combined** set at assignment time, not
per-rubric at save time.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `event_id` | int, FK → `events.id` | No longer unique — an event can hold several rubrics |
| `name` | str | e.g. `"Technical"`, `"Presentation"` |
| `criteria` | JSON list[dict] | Each item: `{key, label, weight, max_score}`. The rubric **locks** (`PUT`/`DELETE` return `409`) once any score exists for the event — see JUDGING.md |
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

### `stored_files` (`api/app/storage/models.py`)

Polymorphic ownership: `(owner_type, owner_id)` is unique, so an owner (a submission or a
user) has at most one current file — uploading a replacement deletes the old one. Content
lives on local disk behind the `StorageService` interface (`api/app/storage/service.py`);
this table only tracks metadata. Keys are server-generated (`uuid4().hex` + an extension
derived from the validated content-type), never taken from the client's filename, so a
client can't path-traverse or overwrite an arbitrary key (see THREAT-MODEL.md).

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `owner_type` | str | `"submission"` \| `"user"` |
| `owner_id` | int | The submission or user id |
| `key` | str | Server-generated storage key; also the on-disk filename |
| `content_type` | str | Validated at upload time against an image allow-list |
| `created_at` | timestamptz | |

Unique constraint: `(owner_type, owner_id)`.

### `webhook_subscriptions` (`api/app/webhooks/models.py`)

Opt-in per event (PLAN.md Phase 7.3) — zero outbound calls unless an organizer configures
one. Delivery is fire-and-forget via FastAPI `BackgroundTasks`, single attempt, no retry
queue (a deliberate scope cut: "a retry system is real infrastructure this hackathon-scale
platform does not need").

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `event_id` | int, FK → `events.id` | |
| `url` | str | Must start with `http://` or `https://`, max 500 chars |
| `created_by_id` | int, FK → `users.id` | Must be `organizer` or `admin` |
| `active` | bool | Default `true`; there is no separate deactivate toggle — deleting the row is how a subscription is turned off |
| `last_status` | str | `"never fired"` \| `"delivered"` \| `"failed"`, updated after each delivery attempt |
| `created_at` | timestamptz | |

Payload topics: `submission.submitted`, `assignments.run`, `score.submitted`,
`event.results_revealed`. Every payload is signed with the same Ed25519 key used for judge
participation records (`api/app/crypto.py`'s `sign_record()`), verifiable offline against
`GET /api/public-key`.

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
events ──< rubrics (one-to-many)
events ──< judge_assignments >── submissions
users (judges) ──< judge_assignments
judge_assignments ──< scores (one-to-one)
users ──< votes >── submissions
users ──< comments >── submissions
users ──< audit_log (nullable actor)
submissions ──< stored_files (owner_type="submission")
users ──< stored_files (owner_type="user")
events ──< webhook_subscriptions
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
- **Uploaded images**: not part of bulk event export/import — a `stored_files` row's
  content lives only on the API container's local disk, so restoring an export into a
  different environment restores data, not the accompanying images (see ARCHITECTURE.md).
