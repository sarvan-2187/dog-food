# DATA-MODEL.md — HackFlow

Schema documentation for the tables SQLModel creates from `api/app/*/models.py`. All
timestamps are `TIMESTAMP WITH TIME ZONE` (see `api/app/timeutil.py`'s `utcnow()`) so a
client's local offset never drifts against the server's enforcement of a deadline — this
was a real bug (audit finding #1 in PLAN.md) before it was fixed.

There is no migration tool in this build (see PLAN.md Open Questions). `SQLModel.metadata.
create_all()` only creates missing tables, so three idempotent boot steps in
`api/app/db.py` upgrade an existing volume in place:
- `add_missing_columns()` adds new columns, only when `information_schema` says they're
  absent.
- `add_guarded_indexes()` creates the one-team-per-event index once the data allows it.
- `run_backfills()` fills new columns for old rows.

See ARCHITECTURE.md. `docker compose down -v` is only needed for a clean slate.

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
| `session_version` | int, default 0 | Signed into every session cookie; incremented on each password change or reset, which invalidates every older cookie at once (PLAN.md Phase 9.1) |
| `is_active` | bool, default true | False blocks sign-in and, with a `session_version` bump, ends every session at once. Admin accounts can't be deactivated (Phase 10.10) |
| `email_verified_at` | timestamptz, nullable | Set when the owner follows a signed 24-hour link from `POST /api/auth/verify-email`; fixture accounts are seeded verified. An event can require it to vote (docs/THREAT-MODEL.md entry 25) |

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

### `api_keys` (`api/app/auth/api_keys.py`)

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `user_id` | int, FK → `users.id` | The organizer or admin the key acts as |
| `name` | str | The owner's label, e.g. "Discord bot" |
| `hint` | str | First 6 characters after `hf_`, so the owner can tell keys apart |
| `key_hash` | str, unique | SHA-256 of the key; the key itself is never stored |
| `created_at`, `last_used_at`, `revoked_at` | timestamptz | `last_used_at` is refreshed at most every 5 minutes; a revoked key never authenticates again |

A request authenticates with `Authorization: Bearer hf_...` instead of the session cookie. The key's owner must still be active and an organizer or admin.

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
| `voting_access` | str | `authenticated` (default), `email` or `open` - who may vote; see `voting/voter.py` and docs/THREAT-MODEL.md entry 25. `email` is refused while SMTP is off |
| `voting_requires_verified` | bool, default false | Account voters need `users.email_verified_at`. Refused (409) while SMTP is off, since nobody could verify |
| `voting_account_cutoff` | timestamptz, nullable | Accounts created at or after this can't vote. Needs no email |
| `results_hidden_until` | timestamptz, nullable | Gates who may see vote counts and standings — enforced in the API response itself, not just hidden in the UI |
| `results_revealed_notified` | bool | One-shot guard so the `event.results_revealed` webhook topic fires exactly once, flipped the first time `public_results` is read after `results_are_public()` goes true (PLAN.md Phase 7.3) |
| `judging_deadline` | timestamptz, nullable | Soft: shown to judges and organizers, must be after `end_at`. A score saved after it is recorded with `late: true` in the audit log, never refused |
| `created_by_id` | int, FK → `users.id` | Must be `organizer` or `admin` |
| `created_at` | timestamptz | |
| `status` | str | `draft` \| `published`. New and imported events start as drafts, which are hidden (404) from everyone but organizers; existing events were backfilled as published (Phase 10.12) |
| `rules` | str | Plain text shown on the event page, never rendered as HTML (Phase 10.8) |
| `stages` | JSON list | Named rounds shown as a timeline on the event page: `[{"name", "description", "starts_at", "ends_at"}]`, ISO-8601 UTC, at most 10, sorted by start. Informational: the server's gates are still `start_at` / `end_at` / `results_hidden_until`. Included in event export/import |

### `announcements` (`api/app/events/models.py`)

An organizer's message to an event's participants (Phase 10.11). Plain text, never
rendered as HTML.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `event_id` | int, FK → `events.id` | |
| `author_id` | int, FK → `users.id` | Organizer or admin |
| `title`, `body` | str | 3–120 and 1–2000 characters |
| `emailed_count` | int | How many participants it was emailed to (0 when email is off) |
| `created_at`, `updated_at` | timestamptz | |

### `teams` / `team_memberships` (`api/app/teams/models.py`)

One event has many teams; one team has many members via the join table.

| `teams` column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `event_id` | int, FK → `events.id` | |
| `name` | str | |
| `invite_code` | str, unique | `secrets.token_urlsafe(6)`, generated on team creation |
| `invite_code_expires_at` | timestamptz | Defaults to 30 days out; checked server-side on redemption, not just hidden in the UI. The captain can replace the code, which kills the old link at once |
| `created_at` | timestamptz | |
| `captain_id` | int, FK → `users.id`, nullable | The creator; may rename, remove members, hand the role on and replace the invite link. Passes to the earliest remaining member if the captain leaves (Phase 10.9) |

| `team_memberships` column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `team_id` | int, FK → `teams.id` | |
| `user_id` | int, FK → `users.id` | |
| `joined_at` | timestamptz | |
| `event_id` | int, FK → `events.id` | Copied from the team by a `before_insert` listener, so callers never set it |

Unique constraints: `(team_id, user_id)` — a user can't join the same team twice — and
`(event_id, user_id)`, one team per person per event (Phase 10.2). The second is created at
boot only when existing data already satisfies it; until then the admin Users page lists
the duplicates.

### `submissions` (`api/app/submissions/models.py`)

**One submission per team**, not per user — see PLAN.md Open Questions for the rationale
(matches how a hackathon typically judges a team's single entry).

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `team_id` | int, FK → `teams.id`, **unique** | Enforces the one-per-team rule at the DB level |
| `event_id` | int, FK → `events.id` | Denormalized for query convenience |
| `title`, `description`, `track` | str | |
| `repo_url`, `demo_url`, `video_url` | str | Optional; `http`/`https` only, at most 500 characters, validated on save and on import. Shown as links, never embedded (Phase 10.5) |
| `status` | enum | `draft` \| `submitted`. Only `submitted` rows appear in the public gallery |
| `disqualified_at` | timestamptz, nullable | Set by an organizer's eligibility ruling. A disqualified entry leaves the gallery, voting, assignment, awards and standings (`in_competition()` in `submissions/models.py`); its scores are kept so reinstating restores it. A column, not a status value, so reinstating never loses `draft`/`submitted` |
| `disqualified_reason` | str | Shown to the team. Required to disqualify |
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
| `criteria` | JSON list[dict] | Each item: `{key, label, weight, max_score, description?}`; `description` (Phase 10.8) is shown to judges and, with the weight, to entrants. The rubric **locks** (`PUT`/`DELETE` return `409`) once any score exists for the event — see JUDGING.md |
| `created_at`, `updated_at` | timestamptz | |

### `judge_invites` (`api/app/judging/models.py`)

The only routes into the `judge` and `organizer` roles besides the seed data.
Single-use, expiring and revocable.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `token` | str, unique | `secrets.token_urlsafe(16)`, the part of the link that grants the role |
| `invited_email`, `note` | str | For the issuer's own records; redemption isn't tied to the email |
| `created_by_id` | int, FK → `users.id` | Organizer/admin (judge invitations); admin only (organizer invitations) |
| `expires_at` | timestamptz | 1–90 days out |
| `redeemed_at`, `redeemed_by_id` | nullable | Set once, on redemption |
| `event_id` | int, FK → `events.id`, nullable | The event a judge invitation is for; redeeming it adds the judge to that event's panel. Null on organizer invitations and on pre-Phase-10 judge invitations |
| `grants_role` | str | `judge` \| `organizer` (Phase 10.10) |
| `created_at` | timestamptz | |

### `event_judges` (`api/app/judging/models.py`)

An event's judge panel (Phase 10.1). Assignment draws only from here, never from every
judge on the platform.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `event_id` | int, FK → `events.id` | |
| `user_id` | int, FK → `users.id` | Must hold the `judge` role to be assigned |
| `added_by_id` | int, FK → `users.id`, nullable | |
| `added_at` | timestamptz | |

Unique constraint: `(event_id, user_id)`. Backfilled at boot from existing assignments.

### `judge_conflicts` (`api/app/judging/models.py`)

A judge's declared conflict of interest with one submission (Phase 10.7). Assignment treats
it exactly like a same-team conflict, so the submission is never handed back to them.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `event_id`, `judge_id`, `submission_id` | int, FK | |
| `reason` | str | Optional, up to 300 characters; shown to the organizer |
| `created_at` | timestamptz | |

Unique constraint: `(judge_id, submission_id)`.

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
idempotent and blocks double-assignment. Removing a judge from an event deletes their
*unscored* assignments; scored ones stay (Phase 10.7).

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

### `awards` (`api/app/scoring/models.py`)

One configured prize given to one submission (Phase 10.6). Hidden until results are
visible, through the same `may_see_results` gate as the standings.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `event_id` | int, FK → `events.id` | |
| `prize_rank` | str | The prize's label from `events.prize_config` ("1st Place", "Best Developer Tool") |
| `submission_id` | int, FK → `submissions.id` | Must be a submitted entry in the same event |
| `note` | str | Optional, shown with the winner |
| `awarded_by_id` | int, FK → `users.id` | |
| `updated_at` | timestamptz | |

Unique constraint: `(event_id, prize_rank)`. A submission may win more than one prize.

### `votes` / `comments` (`api/app/voting/models.py`)

| `votes` column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `event_id`, `submission_id` | int, FK | |
| `user_id` | int, FK, nullable | `NULL` for a guest vote (`voting_access` `open` or `email`) |
| `voter_key` | str | `email:<sha256>` for accounts and email-confirmed guests (so one address is one voter either way), `anon:<random>` for open-link guests |
| `fingerprint_hash` | str | `sha256(client-ip \| user-agent)`, truncated — a **soft** flag only, never a block (see JUDGING.md) |
| `created_at` | timestamptz | |

Unique constraints: `(user_id, submission_id)` and `(voter_key, submission_id)` — the **hard** duplicate-vote guards;
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
client can't path-traverse or overwrite an arbitrary key (see docs/THREAT-MODEL.md).

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
`event.results_revealed`, `announcement.posted`. Every payload is signed with the same Ed25519 key used for judge
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
users ──< team_memberships >── teams ──< events   (one membership per user per event)
teams >── users (captain)
users ──< submissions (via teams, one-to-one with team)
users ──< password_resets
events ──< rubrics (one-to-many)
events ──< judge_invites (judge invitations; organizer invitations have no event)
events ──< event_judges >── users (judges)        (the event's judge panel)
events ──< judge_assignments >── submissions
users (judges) ──< judge_assignments
users (judges) ──< judge_conflicts >── submissions
judge_assignments ──< scores (one-to-one)
events ──< awards >── submissions
events ──< announcements
users ──< votes >── submissions
users ──< comments >── submissions
users ──< audit_log (nullable actor)
submissions ──< stored_files (owner_type="submission")
users ──< stored_files (owner_type="user")
events ──< webhook_subscriptions
```

## Import / export paths

- **Fixture seeding** (`api/app/seed.py`): `fixtures/users.json` → `fixtures/events.json`
  → `fixtures/teams.json` → `fixtures/submissions.json` → `fixtures/rubrics.json` → event
  judge panels (each event's `judge_emails`), in that order, since each step needs the
  previous step's generated ids. Every insert is guarded
  by a lookup on the row's natural key, so re-running on an already-seeded database is a
  no-op.
- **CSV export** (`api/app/scoring/router.py`, stdlib `csv` only): `users.csv`,
  `submissions.csv` (including `repo_url`, `demo_url`, `video_url`), `assignments.csv`,
  `scores.csv`, `results.csv` per event, organizer/admin only (see
  `test_role_isolation.py`).
- **Event backup** (`GET /api/events/{id}/export.json` / `POST /api/events/import`): the
  event's config (including `rules`), rubrics, teams and submissions (including links).
  Imports arrive as drafts, and links are validated with the same http(s)-only rule as the
  submission form. Judge panels, assignments, scores and awards are deliberately not
  carried over: they belong to specific judge accounts.
- **Uploaded images**: not part of bulk event export/import — a `stored_files` row's
  content lives only on the API container's local disk, so restoring an export into a
  different environment restores data, not the accompanying images (see ARCHITECTURE.md).
