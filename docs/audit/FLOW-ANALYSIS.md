# Flow analysis: the ten stages, gate by gate

The README describes HackFlow as ten stages, from registration to archive. This document
checks each one the way an attacker or an unlucky user would meet it: what goes in, what
the **server** enforces before handing data to the next stage, what could go wrong, and
which test proves the gate holds. Findings refer to [`SECURITY-AUDIT.md`](SECURITY-AUDIT.md)
(S#) and [`LOGIC-REVIEW.md`](LOGIC-REVIEW.md) (L#).

```text
 1 Registration ─► 2 Teams ─► 3 Submissions ═(deadline)═► 4 Eligibility ═(competing only)═►
 5 Assignment ═(judging opens)═► 6 Scoring ─(raw totals)─► 7 Normalization ─(standings)─►
 8 Results ═(reveal time)═► 9 Certificates ─► 10 Archive
 ═ = a gate the server enforces; a request that ignores the UI still meets it
```

Before any stage, every request passes the edge guards (`protection.py`,
`request_limit.py`, `serve.py`): body and header caps, a header timeout against
slow-loris, and a limit of 200 requests a minute per signed-in account or anonymous address,
under a per-IP ceiling. Static files count only towards the ceiling (S12).

---

## 1. Registration

| | |
|---|---|
| **How** | `POST /api/auth/register`, `POST /api/auth/login` |
| **Server gates** | Sign-up always creates a `participant`; other roles come only by invitation or the seed. bcrypt, and passwords over 72 bytes are refused (S9). Failed logins are throttled per account and per address *before* the password is checked, and unknown emails cost the same bcrypt time (no timing oracle). Sign-up is throttled per address. |
| **Hands on** | A signed session cookie carrying `session_version`, so a password change signs out every device. The secret is generated per install if unset (S1). |
| **Went wrong before** | Case-variant duplicate accounts (L1); forgeable sessions from the default secret (S1); spoofable client address behind a proxy (S7); cookies not `Secure` on https (S6) |
| **Tests** | `test_auth.py`, `test_password_reset.py`, `test_logic_fixes.py`, `test_security.py` |

## 2. Team formation

| | |
|---|---|
| **How** | `POST /api/events/{id}/teams`, `POST /api/teams/join`, captain actions under `/api/teams/{id}` |
| **Server gates** | One team per person per event (API check plus a unique index). Size cap, checked under a row lock (L4). Team and first membership are created in one transaction (L3). Invite links expire. Everything freezes at the deadline. Only the captain manages the team. |
| **Hands on** | Memberships, which feed the conflict set (stage 5) and the certificate's names (stage 9) |
| **Tests** | `test_teams.py`, `test_phase10.py`, `test_logic_fixes.py`, browser `lifecycle.spec.ts` |

## 3. Project submissions

| | |
|---|---|
| **How** | `PATCH /api/teams/{id}/submission` (autosave), `POST .../submit`, image routes |
| **Server gates** | **The deadline is enforced on the server** on every write, which the DOGFOOD checker probes. Required fields and required custom questions must be filled before Submit. Links must be http(s). Lengths are capped. Images need an allowed type, magic bytes that match it, at most 5 MB each and at most 5 per project. The track must be one of the event's (L10). |
| **Hands on** | A `submitted` entry, frozen at the deadline |
| **Went wrong before** | **L9:** the legacy "replace image 1" route ignored the deadline, so a team could change its thumbnail during judging. |
| **Tests** | `test_submissions.py`, `test_submission_fields.py`, `test_storage.py`, `test_ported_fixes.py`, checker T1 |

## 4. Eligibility verification

| | |
|---|---|
| **How** | `GET /api/events/{id}/eligibility`, `POST /api/submissions/{id}/eligibility` |
| **Server gates** | Automatic flags only *inform*; a human disqualifies, with a reason the team sees. One predicate, `in_competition()`, filters the gallery, voting, assignment, awards and standings together. Reinstating restores the entry's scores. |
| **Hands on** | The set of competing entries |
| **Note** | The duplicate-repository flag normalizes case, a trailing `/` and `.git`, but not `http`/`https` or `www.`. That is low risk, because flags never act on their own. L10 makes the "No track chosen" flag trustworthy. |
| **Tests** | `test_eligibility.py`, `test_regressions.py` |

## 5. Judge assignment

| | |
|---|---|
| **How** | `POST /api/events/{id}/assignments`; judges join through single-use invites |
| **Server gates** | Refused before submissions close. Needs rubric weights adding to 1.0. Uses only the event's own panel. Never assigns a judge their own team or a declared conflict. A track judge only gets their own track. Deterministic, and re-running only fills gaps. |
| **Hands on** | Assignments: the only thing that lets a judge see or score an entry |
| **Tests** | `test_judging.py`, `test_track_judges.py`, `test_judge_invites.py` |

## 6. Scoring

| | |
|---|---|
| **How** | `GET /api/assignments/{id}/sheet`, `PUT /api/assignments/{id}/score` |
| **Server gates** | Judge role, then ownership, then track. Every criterion present, each within 0..max. The rubric locks after the first score. A late score is flagged in the audit log, not refused. A draft event's rubrics aren't readable by outsiders (L13). |
| **Hands on** | `raw_total` per (judge, entry) |
| **Went wrong before** | **L11:** the weighted total ignored each criterion's scale. |
| **Tests** | `test_scoring.py`, `test_role_isolation.py`, checker T2 (peer scores 403, participant 403) |

## 7. Score normalization

| | |
|---|---|
| **How** | Pure functions in `scoring/normalization.py`, recomputed on every read of results |
| **Server gates** | Only competing entries go in, and disqualified ones are removed *before* each judge's mean and spread. Community votes never enter. |
| **Hands on** | z̄ (the ranking value), a display score, and each row's completeness (`judges`, `assigned_judges`, `informative_judges`, L14) |
| **Evidence** | `test_normalization_properties.py` checks the app against an independent implementation, invariance to a judge's harshness, and the fixture table. See [`NORMALIZATION-ANALYSIS.md`](NORMALIZATION-ANALYSIS.md). |
| **Open question** | A judge with no spread (one score, or all equal) contributes z = 0 *to the average*. That shrinks the other judges' signal for the projects that judge scored. Leaving such judges out instead would move 12 fixture ranks by 1–2 places (the top 8 are unchanged). This is a method choice, pinned by the tests above and raised on PR #15. |

## 8. Results

| | |
|---|---|
| **How** | Awards (`PUT /api/events/{id}/awards`, suggested from standings); public winners and results after `results_hidden_until` |
| **Server gates** | One predicate, `may_see_results()`. During the hidden window the *API response* withholds counts and standings (`425 Too Early`), and sorting by votes is refused. |
| **Tests** | `test_voting.py`, `test_vote_integrity.py`, browser `voting.spec.ts` |

## 9. Certificates

| | |
|---|---|
| **How** | `GET /api/submissions/{id}/certificate.pdf`; public check at `/verify` (`GET /api/certificates/{serial}`) |
| **Server gates** | Only the team (or an organizer), and only after the reveal. The PDF is rendered on the server with no external service. Serials are `HF-{id}-{HMAC}`, compared in constant time, and forged, mistyped or not-yet-public serials all give the same 404. Serials were forgeable under the old default secret (S1). |
| **Tests** | `test_phase4.py`, `test_phase10.py` |

## 10. Archive and retrieval

| | |
|---|---|
| **How** | Past events and search; `export.json` / import; five CSV exports; the audit log |
| **Server gates** | Import is all or nothing, never creates or promotes a judge, validates links and numbers (L12), and lands as a draft. CSV cells are safe from formula injection (S4). `users.csv` is scoped to the event's people (S5). The audit log is append-only in the database. Unknown event ids get 404 (L5). |
| **Tests** | `test_event_import_people.py`, `test_audit_append_only.py`, `test_security.py`, browser `event-backup.spec.ts` |

---

## Across every stage: integrations

Every audited action is also a signed webhook topic, and every screen is an API call an
organizer's key can make. Both were run end to end by a separate app,
[Raptor Relay](https://github.com/sarvan-2187/hackflow-third-party). With an API key it:

- read who the key acts as, the events, the gallery and the standings;
- registered its own webhook and received a signed `webhook.test`, `event.updated` and
  `announcement.posted`, all verified against the pinned public key;
- rejected a forged delivery.

See [`WEBHOOKS-AND-API.md`](WEBHOOKS-AND-API.md) and the user manual's "Integrations"
section.
