# Close HackFlow's four known limits

## Context
README "Known limits" lists four gaps: no embeddable gallery widget (blocks a T4 claim), no
eligibility/disqualification step, sybil voting via multiple accounts (THREAT-MODEL #25), and
no judging deadline. Goal: close each with the smallest correct change, before the code freeze
(Sep 28, 18:00 UTC).

**Constraint (user-chosen):** DOGFOOD rules. `docker compose up` must still work fully offline,
seeded, with no hosted services. Every new setting defaults to off or null, so behaviour
without email and the acceptance checker (`/api/gallery` route and the rest) stay unchanged.

**Decisions made:** all four fixes in a lean version; voting defence is *verified email + account
cutoff + organizer void*; the judging deadline is *soft* (shown and flagged, never locks scoring).

Schema changes go through `_ADDED_COLUMNS` in `api/app/db.py` (add-only, idempotent). No
enum changes: `SubmissionStatus` may be a native Postgres ENUM, so disqualification is a
separate column rather than a new status value.

Work on branch `feat/known-limits`, one commit per limit. First step: save this design as
`docs/superpowers/specs/2026-09-27-known-limits-design.md` (brainstorming flow).

---

## 1. Eligibility review / disqualification

- **Schema:** `submissions.disqualified_at timestamptz NULL`, `submissions.disqualified_reason varchar NOT NULL DEFAULT ''`
  (model: `api/app/submissions/models.py`).
- **One shared predicate** in `submissions/models.py`:
  `def in_competition()` returns the clause `status == submitted AND disqualified_at IS NULL`.
  It replaces the bare `status == submitted` checks at:
  - `submissions/router.py`: 131 (gallery) and 213 (public detail)
  - `judging/router.py`: 201 (`run_assignment`)
  - `voting/router.py`: 63 (`_votable_submission`) and 355 (`public_results`)
  - `scoring/awards.py`: 97 and 187

  Keep `teams/router.py:181` as is: a disqualified entry still blocks its last member from leaving.
- **Standings:** in `scoring/router.py` `_raw_by_judge`, add a filter that drops scores for
  disqualified submissions. Normalization then recomputes without them, which is correct:
  judges' z-scores shouldn't include a removed entry. Update the note in JUDGING.md.
- **Endpoint:** `POST /api/submissions/{id}/eligibility`, body `{eligible: bool, reason: str}`,
  guarded by `require_role(*ORGANIZER)`.
  - Disqualifying requires a reason. Reinstating clears it.
  - Disqualifying deletes that submission's *unscored* `JudgeAssignment` rows. Scores are kept,
    so a reinstated entry recovers its reviews.
  - Record `submission.disqualified` or `submission.reinstated` with `audit.log.record` and
    call `notify(...)` for webhooks.
- **Team view:** add `disqualified_reason` to `SubmissionPublic` (`_public`, submissions/router.py:43).
  The team's submission page shows a banner with the reason. The gallery hides the entry.
- **Organizer UI:** a "Disqualify / Reinstate" action with a reason prompt on the organizer's
  submission list in the event results page (`web/src/pages/EventResultsPage.tsx`), plus a
  "Disqualified" count.

## 2. Judging deadline (soft)

- **Schema:** `events.judging_deadline timestamptz NULL` (`api/app/events/models.py`), editable via
  `PATCH /api/events/{id}` (`events/router.py:151`). The deadline must be after `end_at`, otherwise 422.
- **API surface:**
  - `AssignmentPublic.due_at`, set in `_to_public` in `judging/router.py`, which already loads the event.
  - `JudgeEvent.judging_deadline` (`judging/event_judges.py:333`).
  - `EventJudges.judging_deadline` (`list_event_judges`, :66).
- **Late scores:** they still save. The score-submit audit record gets `late=True` when
  `utcnow() > deadline`.
- **Reminder email** (`remind_judge`, event_judges.py:219): include "Due {date}" when a deadline is set.
- **UI:**
  - `JudgeDashboardPage.tsx`: "Due {date} · N days left", or "Overdue" (danger colour), on the list
    header and in the "Coming up" card. Same in the judge view in `DashboardPage.tsx:147`.
  - `JudgePanelCard.tsx`: show the deadline, and mark judges with pending work after it as "Overdue".
  - Event settings: a date-time input next to the existing date fields.
  - Types in `web/src/types.ts`.

## 3. Voting integrity (verified email + account cutoff + void)

- **Schema:**
  - `users.email_verified_at timestamptz NULL`. The seed marks fixture users verified.
  - `events.voting_requires_verified boolean NOT NULL DEFAULT false`
  - `events.voting_account_cutoff timestamptz NULL`
- **Verify flow**, reusing the stateless `URLSafeTimedSerializer` token pattern in `voting/voter.py`
  and the mailer in `auth/mailer.py`:
  - `POST /api/me/verify-email`: rate-limited with the existing `TokenBucketLimiter`. Returns 409 when
    `mailer.CONFIG.enabled` is false.
  - `GET /api/verify-email/confirm?token=`: sets `email_verified_at`, records an audit entry, and
    redirects to `/profile?verified=1`.
  - Profile page: a "Verify email" button with the verified state shown.
- **Enforcement** in `cast_vote` (`voting/router.py`), for account voters only. Email-mode guests
  already proved their address.
  - If `voting_requires_verified` is set and the account isn't verified: 403, "Verify your email to vote".
  - If a cutoff is set and `user.created_at >= voting_account_cutoff`: 403, "Account created after voting eligibility closed".
- **PATCH event:** turning on `voting_requires_verified` while email is off returns 409 ("nobody could
  verify"). The account cutoff works fully offline.
- **Organizer void:**
  - `GET /api/events/{id}/votes/flagged` lists votes whose `fingerprint_hash` is shared by more
    than one `voter_key`. This builds on the existing `vote.duplicate_fingerprint_flagged` signal.
  - `DELETE /api/events/{id}/votes/{vote_id}` records `vote.voided` with the full vote row in the
    audit detail. Both endpoints are organizer-only.
  - UI: a "Suspicious votes" card on `EventResultsPage.tsx` with Void buttons.
  - Event settings gets the two new voting options.
- Update THREAT-MODEL #25 to "Mostly stopped when enabled", naming what's still open: a person with
  several *verified* inboxes who registered before the cutoff.

## 4. Embeddable gallery widget (T4)

- **New module `api/app/embed.py`** with `GET /embed/events/{slug}`: a server-rendered, self-contained
  HTML page with inline CSS and no JS, no new dependency.
  - Builds the page by calling the existing `gallery()` function (`submissions/router.py:117`) with
    `user=None, order="recent"`. Vote counts are therefore withheld exactly as on the public API.
  - All text goes through `html.escape`. Cards show image, title, track and awards, and link to the
    project page on `mailer.APP_BASE_URL` with `target="_blank" rel="noopener"`.
  - Unknown or unpublished event: 404 page.
  - Include the router in `main.py` before the SPA catch-all, and add `"embed/"` to `API_PREFIXES`
    handling as needed.
- **Security headers** (new, small middleware in `main.py`):
  - Every response: `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'`.
    This fixes clickjacking; currently the whole app can be framed by any site.
  - `/embed/*` only: `frame-ancestors *`, with no X-Frame-Options.
  - Add a THREAT-MODEL entry for clickjacking.
- **Organizer UI:** an "Embed on your site" box in event settings with a copyable
  `<iframe src="{APP_BASE_URL}/embed/events/{slug}" …>` snippet.
- **T4 claim:** before adding `"T4"` to `.dogfood.toml` `claimed`, confirm every T4 item exists
  (API/webhooks, certificates, signed records, widget, bulk import/export), and run the acceptance
  checker. Claim T4 only if the report passes it. Regenerate `acceptance-report.txt`.

---

## Docs
- README: rewrite "Known limits" (remove the four entries, keep any honest residue such as "several
  verified inboxes before the cutoff"). Also update the status paragraph (~line 282) and the
  THREAT-MODEL count (~line 298).
- THREAT-MODEL.md: #25 plus a new clickjacking entry.
- JUDGING.md: disqualification effect on normalization, and the soft deadline.
- DATA-MODEL.md: the new columns.
- USER-MANUAL.md:
  - organizer steps for disqualify, deadline, voting options, void, embed;
  - judge "due date" text;
  - participant "verify email" and disqualification banner.

## Tests (one file per limit, existing `client`/`session` fixtures in `api/tests/conftest.py`)
- `test_eligibility.py`
  - A disqualified entry is gone from the gallery, public detail, voting (404), awards and standings.
  - Its unscored assignments are removed, and reinstating restores it.
  - Non-organizers get 403, and a missing reason returns 422.
- `test_judging_deadline.py`
  - Validation that the deadline is after `end_at`.
  - `due_at` appears on assignments.
  - A late score saves and its audit record has `late=True`.
- `test_vote_integrity.py`
  - An unverified or post-cutoff account is refused (403) only when the setting is on.
  - Verify-token round trip.
  - Turning on the verified requirement with email off returns 409.
  - The flagged list and void (audit entry written, count drops).
- `test_embed.py`
  - 200 HTML for a published event, 404 for a draft event.
  - Titles are escaped (`<script>` title renders inert).
  - No vote counts while results are hidden.
  - Frame headers: `/embed` frameable, `/` and `/api/*` DENY.

## Verification
1. `docker compose up --build` on a fresh volume (`down -v`), with network off. It must seed and run
   with no email configured.
2. `docker compose exec api pytest` passes: 467 existing tests plus the new ones.
3. The acceptance checker still passes 7/7 (plus T4 if claimed). Update `acceptance-report.txt`.
4. Browser pass on localhost:8000:
   - Disqualify and reinstate an entry in `judging-showcase-2026`, and watch the gallery and standings change.
   - Set a judging deadline, then log in as judge `sam@` and see the due date.
   - Turn on the account cutoff and see a new participant's vote refused.
   - Paste the iframe snippet into a local HTML file and see the widget render.
   - Screenshot each.
5. Existing Playwright specs (`web/tests`) still pass.
