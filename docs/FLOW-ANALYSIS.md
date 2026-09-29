# Flow analysis: the ten stages, gate by gate

The README describes HackFlow as ten stages, from registration to archive. This document
checks each stage the way an attacker or an unlucky user would meet it: what goes in, what
the **server** enforces before handing data to the next stage, what could go wrong, and
which test proves the gate holds. It was written during the 2026-09-29 audit. Problems it
found are marked **Fixed** and cross-referenced to
[`SECURITY-AUDIT.md`](SECURITY-AUDIT.md) (S#) or
[`NORMALIZATION-ANALYSIS.md`](NORMALIZATION-ANALYSIS.md) (L#).

```text
 1 Registration ─► 2 Teams ─► 3 Submissions ═(deadline)═► 4 Eligibility ═(competing only)═►
 5 Assignment ═(judging opens)═► 6 Scoring ─(raw totals)─► 7 Normalization ─(standings)─►
 8 Results ═(reveal time)═► 9 Certificates ─► 10 Archive
 ═ = a gate the server enforces; a request that ignores the UI still meets it
```

Every stage was exercised live on a seeded stack. The backend has 457 tests, the browser
has 121 (all passing), and the DOGFOOD checker reports 7/7
([`ACCEPTANCE-REPORT.md`](ACCEPTANCE-REPORT.md)).

---

## 1. Registration

| | |
|---|---|
| **Who / how** | Anyone. `POST /api/auth/register`, `POST /api/auth/login` |
| **Server gates** | Public sign-up always creates a `participant`; judge, organizer and admin come only by invitation or the seed. Passwords are 8+ characters, bcrypt. Failed logins: 10 per account and 30 per address per 15 min, checked *before* the password (a guess that is right but throttled still fails). Unknown emails cost the same bcrypt time as known ones (no timing oracle). |
| **Hands on** | A signed session cookie (`session_version` inside, so a password change signs out every device) |
| **Failure modes checked** | Self-promotion to judge (refused: `test_auth.py`); duplicate accounts; brute force; account enumeration by timing or message |
| **Found in this audit** | **Fixed S6:** `Alice@x.com` and `alice@x.com` were two accounts, and login was case-sensitive. **Fixed S7:** sign-up was unthrottled (bcrypt CPU, sybil accounts). **Fixed S5:** behind Render's proxy the per-address login limit was *site-wide*, so 30 bad guesses from anyone locked everyone out. **Fixed S14:** cookies weren't `Secure` on https. |
| **Tests** | `test_auth.py`, `test_password_reset.py` (29), `test_protection.py` (email case, sign-up limit, proxy address) |

## 2. Team formation

| | |
|---|---|
| **Who / how** | Participants. `POST /api/events/{id}/teams`, `POST /api/teams/join` (invite code), captain actions under `/api/teams/{id}` |
| **Server gates** | One team per person per event (API check plus a unique index on `(event_id, user_id)`). Size cap from `Event.max_team_size`. Invite codes expire. Nothing changes after the deadline. Only the captain renames, removes, hands over or re-keys the link. The last member can't leave a team that has submitted. |
| **Hands on** | `Team` + `TeamMembership` rows, which later feed the conflict set (stage 5) and the certificate's member list (stage 9) |
| **Failure modes checked** | Joining two teams; joining after the deadline; expired or replaced links; a non-captain acting as captain |
| **Found in this audit** | **Fixed S11:** the size cap was check-then-insert, so two simultaneous joins could both take the last seat. The team row is now locked (`FOR UPDATE`) before counting. |
| **Tests** | `test_teams.py`, `test_phase10.py` (team management), browser `lifecycle.spec.ts` |

## 3. Project submissions

| | |
|---|---|
| **Who / how** | Team members. `PATCH /api/teams/{id}/submission` (autosave), `POST .../submit`, image routes |
| **Server gates** | **The deadline is checked on the server** (`_load_open_event`): every write after `end_at` is refused with 400. The DOGFOOD checker probes exactly this. Title and description are required to submit, and so are required custom questions. Links must be http(s) (no `javascript:`). Field lengths are capped. Images must be PNG/JPEG/WebP/GIF, 5 MB or less, with magic bytes matching the declared type, at most 5 per project. |
| **Hands on** | A `submitted` entry, frozen at the deadline |
| **Failure modes checked** | Late edits (checker T1: PASS); script links; fake image types; answers to questions the event doesn't have |
| **Found in this audit** | **Fixed S8:** the legacy "replace image 1" route skipped the deadline, so a team could change its thumbnail during judging. **Fixed S9/L5:** `track` was free text, so an invented track dodged the "No track chosen" flag and track-judge routing. **Fixed S3:** uploads were read fully into memory before the size check. |
| **Tests** | `test_submissions.py`, `test_submission_fields.py`, `test_storage.py`, `test_protection.py` (track, frozen legacy upload), `test_dogfood_checker.py` |

## 4. Eligibility verification

| | |
|---|---|
| **Who / how** | Organizers. `GET /api/events/{id}/eligibility`, `POST /api/submissions/{id}/eligibility` |
| **Server gates** | Automatic flags (no repo, duplicate repo, thin description, no track, over the size cap) only *inform*. A human disqualifies, with a reason the team sees. One predicate, `in_competition()`, filters the gallery, voting, assignment, awards and standings, so a disqualified entry leaves all of them at once. |
| **Hands on** | The set of competing entries |
| **Failure modes checked** | A disqualified entry lingering in one list but not another; reinstatement losing its scores (scores are kept, and unscored assignments are released) |
| **Found in this audit** | The duplicate-repo check normalizes case, a trailing `/` and `.git`, but not `http` vs `https` or `www.`. Low risk because flags only inform (noted, not changed). The track fix in stage 3 makes the "No track chosen" flag trustworthy. |
| **Tests** | `test_eligibility.py`, `test_regressions.py` |

## 5. Judge assignment

| | |
|---|---|
| **Who / how** | Organizers. `POST /api/events/{id}/assignments` (judges join via single-use invites, `judging/invites.py`) |
| **Server gates** | Refused before `end_at` (judges score only final work). Needs a rubric set whose weights add to 1.0. Only the event's own panel is used. A judge never gets their own team's entry or a declared conflict. A track judge only gets their track, and untracked entries go to untracked judges. Deterministic. Re-running only fills gaps. |
| **Hands on** | `JudgeAssignment` rows: the only thing that lets a judge see or score an entry |
| **Failure modes checked** | Self-judging (THREAT-MODEL #3); cross-track exposure (DOGFOOD T2); duplicate assignments; a removed judge's unscored work (re-assigned) |
| **Found in this audit** | No defects. The algorithm is greedy by design and reports shortfalls instead of relaxing the conflict rules (JUDGING.md). |
| **Tests** | `test_judging.py`, `test_track_judges.py`, `test_judge_invites.py`, `test_phase10.py` |

## 6. Scoring

| | |
|---|---|
| **Who / how** | The assigned judge only. `GET /api/assignments/{id}/sheet`, `PUT /api/assignments/{id}/score` |
| **Server gates** | `require_role(judge)`, then ownership (`assignment.judge_id == user.id`), then `assert_in_track`. Organizers can't score by calling the endpoint directly. Every criterion must be present, each value between 0 and its max (NaN and ∞ fail the range check). The rubric locks once the first score exists. A score after the soft judging deadline is flagged `late` in the audit log, never refused. |
| **Hands on** | `Score.raw_total` per (judge, entry) |
| **Failure modes checked** | Peer score reads (checker T2: 403, and the attempt is audited); participant access (checker T2: 403); an organizer masquerading as a judge; a rubric edited after scoring |
| **Found in this audit** | **Fixed L1:** the weighted total ignored each criterion's scale, so a 0–100 criterion outweighed a 0–10 one whatever the weights said. |
| **Tests** | `test_scoring.py`, `test_role_isolation.py` (66 parametrized cases), `test_judging_deadline.py`, checker T2 |

## 7. Score normalization

| | |
|---|---|
| **Who / how** | HackFlow, on every read of results (`scoring/normalization.py`, pure functions) |
| **Server gates** | Only competing entries' scores go in, and disqualified ones are removed *before* μ and σ are computed. Community votes never enter. Results are organizer-only until the reveal. |
| **Hands on** | z̄ per entry (the ranking value), a display score, and completeness counts |
| **Failure modes checked** | Divide by zero (σ = 0); harsh or lenient judges; a disqualified entry skewing a judge's mean |
| **Found in this audit** | **Fixed L2:** uninformative judges (σ = 0) were averaged in as 0, diluting z̄ by how many such judges an entry drew. 12 fixture ranks were wrong, the top 8 unaffected. **Fixed L3:** float noise could fake spread. **Fixed L4:** partial data is now explicit (`judges`, `assigned_judges`, `informative_judges` per row). Measured: exactly invariant to a judge's harshness, and the top 10 keeps ≥ 8 of 10 when any one judge is removed. |
| **Tests** | `test_scoring.py` (14, including 5 new) |

## 8. Results

| | |
|---|---|
| **Who / how** | Organizers pick winners (`PUT /api/events/{id}/awards`, suggested from standings). Everyone sees winners and public results after `results_hidden_until` |
| **Server gates** | `may_see_results()` is one predicate used by the gallery, the public results, awards and certificates. During the hidden window the *API response* withholds counts and standings (`425 Too Early` with the reveal time). The UI merely reflects that. Sorting by votes is refused while hidden. |
| **Hands on** | Revealed ranks and awards |
| **Failure modes checked** | Leaking counts through an unauthenticated API call (PLAN.md's named pitfall); judges seeing standings early |
| **Found in this audit** | No defects. The `event.results_revealed` webhook fires lazily on the first read after the reveal. That is documented, and it means "at first read", not "at the exact second". |
| **Tests** | `test_voting.py` (36), `test_vote_integrity.py`, browser `voting.spec.ts` |

## 9. Certificates

| | |
|---|---|
| **Who / how** | Team members and organizers. `GET /api/submissions/{id}/certificate.pdf`. Anyone can check a serial at `GET /api/certificates/{serial}` or `/verify` |
| **Server gates** | Only the submitting team (or an organizer), only after the reveal. Rendered on the server (reportlab), with no external service. The serial is `HF-{id}-{HMAC}`, compared in constant time. A forged, mistyped or not-yet-public serial all give the same 404, so serials can't be used to probe which entries exist. |
| **Hands on** | A verifiable PDF |
| **Failure modes checked** | Downloading another team's certificate; guessing serials; certificates before the reveal |
| **Found in this audit** | The HMAC key is the session secret, so the dev-default `SESSION_SECRET` makes serials forgeable too. That is one more reason for the new boot warning (**S16**) and the deploy checklist's "set a real `SESSION_SECRET`". |
| **Tests** | `test_phase4.py`, `test_phase10.py` |

## 10. Long-term archival and retrieval

| | |
|---|---|
| **Who / how** | Everyone browses past events and search. Organizers export `GET /api/events/{id}/export.json` and the five CSVs, and import with `POST /api/events/import`. |
| **Server gates** | Import is all-or-nothing: every judge, criterion and score must match or nothing is written (a 422 listing up to 10 problems). Judges are matched, never created or promoted. Imported links get the same http(s) rule as the form. Imports land as drafts. The audit log has no write path from any client. |
| **Hands on** | A portable backup, and an audit trail of every consequential action (also sent as webhooks, below) |
| **Failure modes checked** | A hostile backup (script links, over-long fields, fake judges, scores out of range) |
| **Found in this audit** | **Fixed S10/L6:** a backup could carry `max_score: 0` or NaN. **Fixed S3:** the import body is now capped at 10 MB (the 40-project fixture event exports as 46 KB). Also, the scores and assignments CSV exports no longer load every score on the platform to filter in Python. |
| **Tests** | `test_event_import_people.py`, `test_phase4.py`, browser `event-backup.spec.ts` |

---

## Across every stage: integrations

Every audited action above is also a **webhook** topic, and every screen is also an
**API** call that an organizer's key can make. Both were exercised end to end by the
separate [Raptor Relay](https://github.com/sarvan-2187/hackflow-third-party) app: key →
`/api/auth/me` → events, gallery and results → self-registered webhook → signed
`webhook.test`, `event.updated` and `announcement.posted` deliveries, all verified. A forged
delivery was rejected. Found and fixed on the way: webhook SSRF (**S2**), unbounded
fan-out (**S12**) and replayable deliveries (**S13**). See the manual's "Integrations"
section.
