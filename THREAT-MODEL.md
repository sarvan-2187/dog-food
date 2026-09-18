# THREAT-MODEL.md — JudgeR

Bonus challenge (PLAN.md Phase 4): each attack paired with the mitigation
already built, not new work — this is a write-up of what Phases 0–4 already
enforce, cross-checked against the code that enforces it.

| # | Attack | Mitigation already built | Where |
|---|--------|---------------------------|-------|
| 1 | A judge scores another judge's assignment. | `submit_score`/`get_my_score` check `assignment.judge_id != user.id` and refuse with 403 before touching the score row. | `api/app/scoring/router.py` |
| 2 | A participant self-promotes to judge or organizer. | `judge` has no self-service signup path at all — the only route in is a single-use, expiring `JudgeInvite` issued by an organizer/admin. Role changes otherwise only happen server-side. | `api/app/judging/invites.py` |
| 3 | A judge is assigned a submission from their own team (grading themselves). | `build_conflict_set` excludes every (judge, submission) pair where the judge shares a team with that submission, computed from real `TeamMembership` rows before assignment runs — not left to organizer discipline. | `api/app/judging/assignment.py` |
| 4 | An organizer edits rubric weights after scoring starts, invalidating existing scores without anyone noticing. | `upsert_rubric` checks for any `Score` joined through `JudgeAssignment` for the event and refuses the edit with 409 once one exists. | `api/app/judging/router.py` |
| 5 | Results or vote counts leak before the reveal time an organizer promised. | `may_see_results` / `results_are_public` gate every results-bearing endpoint (`/results`, `/public-results`, CSV exports, certificates) server-side against `results_hidden_until` — never just hidden in the UI. Organizers/admins are the one documented exception, since they run the event. | `api/app/events/visibility.py` |
| 6 | A participant votes twice, or a script spams the vote/comment endpoints. | A unique constraint on (submission, voter) blocks duplicate votes at the DB level; a process-global rate limiter throttles comment/vote writes per user. | `api/app/voting/` |
| 7 | Path traversal via a crafted static-file request (`/../../etc/passwd`) reads outside the SPA's static directory. | The SPA catch-all resolves the candidate path and requires `candidate.is_relative_to(STATIC_DIR_RESOLVED)` before serving it. | `api/app/main.py` |
| 8 | A signed judge participation record is edited after issuance (inflating a submissions-scored count) and passed off as genuine. | Records are signed with a server-held Ed25519 key over a canonical (sorted-key) JSON encoding; any byte change fails `verify_record` against the published public key — no server round-trip needed to catch it. | `api/app/crypto.py` |
| 9 | A malicious LIKE-wildcard in a gallery search (`%`, `_`) is used to broaden a search beyond what the query box implies. | Gallery search escapes `%`/`_`/the escape character itself before building the `LIKE` clause. | `api/app/submissions/router.py` |
| 10 | An organizer deletes an event that still has teams/submissions, destroying participant work with one click. | `delete_event` counts dependent teams/submissions first and refuses with a 409 naming the exact count, rather than cascading or hitting a bare FK-violation 500. | `api/app/events/router.py` |
| 11 | A bulk-imported event silently inherits someone else's judge assignments/scores, misattributing who actually judged it. | Import intentionally does not round-trip assignments or scores — only event config, rubric, teams, and submissions. An imported event starts unjudged; assignment and scoring are re-run fresh against real accounts on the new event. | `api/app/scoring/router.py` (`import_event`) |

## What this list does not cover

Denial-of-service, infrastructure-level attacks (the box itself, the network),
and social-engineering of an organizer's own account are out of scope for an
app-layer threat model like this one — see `ARCHITECTURE.md` for the
deployment boundary this app assumes it's running inside.
