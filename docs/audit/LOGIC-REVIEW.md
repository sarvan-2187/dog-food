# Logic review (task 3)

A read of every backend module (`api/app/**`) for behaviour that contradicts
the code's own documented intent. Each fix has a regression test in
`api/tests/test_logic_fixes.py` (L9–L14: `test_ported_fixes.py`); six of those tests fail on the code before
the fix and pass after it.

| # | Where | Problem | Fix |
|---|-------|---------|-----|
| L1 | `auth/router.py` register, login, forgot-password; `auth/recovery.py`; `auth/reset_link.py`; `judging/event_judges.py` | Emails were matched exactly. `Alice@x.org` and `alice@x.org` could register as two accounts, and someone who signed up with a capital letter could not sign in without typing it the same way. The rate-limit keys already lowercased, so the two disagreed. | `find_user_by_email()` (case-insensitive) everywhere a person types an address; new accounts are stored lowercased. Legacy mixed-case rows are still found. |
| L2 | `events/router.py` `delete_event` | An event with no teams or submissions but with a rubric, judge panel, invite, conflict, announcement or webhook could not be deleted: the foreign keys made it a bare 500. | The organizer's own setup rows are deleted with the event. Events with teams or submissions are still refused (409). |
| L3 | `teams/router.py` `create_team` | The team was committed before its first membership. If the membership insert failed (the one-team-per-event index, e.g. two tabs), a memberless team was left behind and the user saw a 500. | Team and membership are one transaction; an index conflict is a 409. |
| L4 | `teams/router.py` `join_team` | The team-size check and the insert were not atomic, so two people redeeming the last seat at once could both get in and overfill the team. | The team row is locked (`SELECT ... FOR UPDATE`) for the check; an index conflict is a 409. |
| L5 | `scoring/router.py` results and all six CSV exports | An unknown event id returned 200 with an empty body, indistinguishable from "nobody has been scored yet". | 404 `Event not found.` |
| L6 | `scoring/router.py` `export_scores`, `export_assignments` | Both loaded every score on the platform and filtered in Python. Correct output, but work grew with every other event. | Queries filtered to the event's assignments. |
| L7 | `submissions/router.py` gallery `order=random` | With no `seed`, every caller got seed 0: one fixed "random" order for everyone, the top-slot bias shuffling exists to remove. The web app always sends a seed, so only API callers saw it. | An unseeded shuffle uses a fresh random seed. A given seed still gives a stable order. |
| L8 | `submissions/router.py` gallery `q` | Search text had no length limit and runs four `ILIKE` scans. | `max_length=200` (422 above it). |
| L9 | `storage/router.py` `POST /api/teams/{id}/submission/image` | The legacy "replace image 1" route skipped the deadline check the other image routes have. A team could swap its thumbnail after submissions closed, while judges were scoring (confirmed live: 200 while `.../images` and `.../submit` returned 400). | Same `_team_submission_open` gate as the other image routes. (PR #15) |
| L10 | `submissions/router.py` autosave | `track` was free text. An invented track dodged the "No track chosen" eligibility flag and sent the entry only to untracked judges (JUDGING.md rule 8). | The track must be one of the event's tracks, or empty. (PR #15) |
| L11 | `scoring/router.py` `_weighted_total` | `sum(w × v)` ignored each criterion's scale: with Technical 0–10 at 70% and Presentation 0–100 at 30%, Presentation carried about 81% of the total. | `sum(w × v / max) / sum(w) × M`, identical to the old total whenever every criterion shares one `max_score` and the weights add to 1 (all fixtures). (PR #15) |
| L12 | `scoring/router.py` event import | A backup's criterion with `max_score: 0` or a non-finite weight was accepted, a division by zero in L11 or NaN in every judge's normalization. | Weights and max scores must be positive and finite, or the import is refused. (PR #15) |
| L13 | `judging/router.py` `GET /api/events/{id}/rubrics` | Any signed-in user could read a draft event's rubrics, which leaked that the draft exists. | 404 unless the event is visible to the caller, like the event itself. (PR #15) |
| L14 | `scoring/router.py` results | Standings are recomputed live from whatever scores exist, but a row didn't say how complete it was (PLAN.md's partial-data pitfall). | Rows and `results.csv` carry `informative_judges` and `assigned_judges`. (PR #15) |

Found in passing and fixed on their own branches: webhook delivery errors
other than `httpx.HTTPError` escaped without recording a status (task 5);
normalization of float-noise spreads and the fixture test's path (task 4);
security findings (task 7, `docs/audit/SECURITY-AUDIT.md`).
