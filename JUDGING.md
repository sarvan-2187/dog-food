# JUDGING.md — Assignment, Normalization & Judging Integrity

## Who evaluates: the role model

`judge` is one of four **distinct** roles (`participant`, `judge`, `organizer`, `admin`),
not a hat a participant puts on. A judge is someone brought onto an event to evaluate; a
participant builds and submits. The two never swap.

There are deliberately **two** evaluation mechanisms in this platform, and they are
separate systems with separate integrity models:

| | **Formal judging** | **Community voting** |
|---|---|---|
| Who acts | `judge` role only, and only on an assignment that is theirs | Any signed-in user, any role |
| Instrument | Weighted rubric, criteria scored 0–`max_score` | One vote per user per submission |
| Integrity model | Role isolation + per-assignment ownership + conflict exclusion + cross-judge normalization | Unique constraint + rate limiting + fingerprint flagging + hidden results |
| Determines the ranking? | Yes — `z_bar_i` is the ranking value | No — a separate public tally |

**Community vote counts never enter the judging pipeline.** `normalize_scores()` consumes
rubric scores and nothing else. "Popular" and "well-executed" are different claims, and
mixing them would make the normalization impossible to defend — which is the one thing a
judging engine cannot afford.

**There is no peer review.** Participants are never asked, or able, to score another
participant's submission. A competitor's hand on a rival's score is exactly the failure
mode the role isolation below exists to prevent, so it is not a feature that was skipped
for time — it is excluded on purpose.

The conflict rule in the next section is easy to misread as implying otherwise. It is a
safeguard for the legitimate overlap case — a mentor who also entered a side project, a
judge who joined a team late — not a hint that judges are drawn from the participant pool.

**Known gap: there is no judge-invitation flow.** Judge accounts currently exist only via
`fixtures/users.json` at boot, so on a live instance an organizer cannot add a judge
without editing a fixture and recreating the database. Every judging path that does exist
is correctly gated and tested; this is a missing capability, not a defect, and it is
tracked in `PLAN.md`'s Open Questions with a scope sketch.

## Assignment algorithm

Implemented in `api/app/judging/assignment.py` as a pure, DB-free function:

```python
assign_judges(submissions, judges, team_memberships, k) -> list[JudgeAssignment]
```

1. **Build a conflict set** — exclude `(judge, submission)` pairs where the judge is a
   member of the submitting team. This is the rule the seeded fixtures exercise for real:
   Dana is both a judge and a member of "Pipeline Pals," so a fresh `docker compose up`
   assigns her every submission *except* her own team's. The fixture exists to prove the
   safeguard works, not to model the intended workflow — see the role model above.
2. **Iterate submissions round-robin**; for each, assign the `k` judges (organizer-
   configurable, default 3) with no conflict and the fewest assignments so far, breaking
   ties by judge ID ascending for determinism.
3. **Deliberately greedy, not a max-flow solver.** If there aren't enough eligible judges
   to reach `k` for every submission, the shortfall is reported via `coverage_report()`
   rather than silently relaxing the conflict rule or leaving it undiscoverable.
4. **Idempotent.** Re-running the assignment for an event that already has assignments
   does not create duplicates — the unique constraint on `(submission_id, judge_id)` is
   the hard guard, and the endpoint reports that nothing was left to do.

## Normalization

Implemented in `api/app/scoring/normalization.py` as a pure function:

```python
normalize_scores(raw_scores_by_judge) -> dict[submission_id, float]
```

```
mu_j    = mean of judge j's raw totals across their assigned submissions
sigma_j = population stddev of judge j's raw totals
z_{j,i} = (x_{j,i} - mu_j) / sigma_j          # if sigma_j == 0, z_{j,i} = 0 for all i from that judge
z_bar_i = mean of z_{j,i} over all judges j who scored submission i
display_i = clamp(50 + 10 * z_bar_i, 0, 100)  # for UI display only; keep z_bar_i as the ranking value
```

This cancels out a judge's individual harshness or leniency — a judge who scores
everything low still ranks submissions correctly relative to each other, because it's
their own mean and spread doing the normalizing, not an absolute scale. `display_i` is
cosmetic (a 0–100 number a human reads); `z_bar_i` is what actually determines rank.

**Why the raw total is `sum(weight × value)`.** Section 8 specifies normalization over
"raw totals" without saying how a raw total is formed from rubric criteria. The weighted
sum keeps the total on the same 0–`max_score` scale as the individual criteria, so "7.8
out of 10" means something to a human reading the CSV export.

Edge cases, each with a dedicated unit test in `api/tests/test_scoring.py`:
- A judge with only one assignment → `sigma_j == 0`, guarded the same way as any
  zero-variance judge: their `z` contributes 0, not a division error.
- A submission scored by only one judge → still produces a valid `z_bar_i`.
- The full fixture dataset (4 judges, varying harshness) → raw mean and normalized
  ranking can genuinely disagree, which is the point of normalizing at all.

## Role isolation

`require_role()` is implemented once in `api/app/auth/deps.py` and imported everywhere —
no route handler duplicates a role check inline. `api/tests/test_role_isolation.py` is a
table-driven 403/401 matrix: every mutating or sensitive-read endpoint, crossed with every
role that must be refused, plus the anonymous case. As of this build that's 66 parametrized
cases, all passing.

Beyond role membership, three endpoints need an **ownership** check on top of the role
check, since "any judge" is not the same as "the assigned judge":
- A judge can only score or view the score for an assignment that is actually theirs —
  `require_role(judge)` alone would let any judge see or overwrite another judge's work.
- An organizer cannot submit a score by calling the judge endpoint directly, even though
  the role check alone wouldn't stop them.
- A participant sees no score detail anywhere, for any submission, including their own
  team's — judging stays confidential until results are released.

The audit log (`GET /api/audit`) is organizer/admin only, and has no write path from any
client-facing endpoint — see DATA-MODEL.md.

## The rubric locks once scoring starts

Changing a rubric's criteria or weights after judges have scored would silently
reinvalidate every score already given against the old weights, with no visible symptom.
`PUT`/`DELETE` on a rubric therefore return `409` with the reason once any score exists
for the event. The alternative — silently recalculating existing scores against new
weights — seemed clearly worse for judging integrity. There is currently no "re-open
scoring" action; an organizer who needs to change a rubric after scoring has begun has to
delete the affected scores first (a deliberate speed bump, not an oversight).

## Results visibility (Phase 3)

`Event.results_hidden_until` gates who may see vote counts and normalized standings, and
it's enforced in the **API response itself** — a request during the hidden window gets a
`425 Too Early` with the reveal time in the body, not `403` (the caller isn't forbidden,
just early) and not a UI that merely hides a number the response already leaked.

`may_see_results()` is one predicate: organizers and admins see counts throughout the
window, because they're running the event and need them; participants, judges, and
anonymous visitors all wait. Judges wait too, deliberately — community vote counts aren't
judging input and shouldn't color a judge's own scoring.

## Duplicate-vote and rate-limit design

- **Hard guard:** the unique constraint on `(user_id, submission_id)` in `votes`,
  enforced by catching the resulting `IntegrityError` rather than a pre-`SELECT` a
  concurrent request could race past.
- **Soft signal:** `fingerprint_hash` (`sha256(client-ip | user-agent)`, truncated) flags
  several votes that look like they came from one client, without ever blocking on it —
  anyone behind one office NAT or mobile network shares a fingerprint, so blocking on it
  would lock out legitimate voters. Treat a flag as "worth a look," never as proof.
- **Rate limiting:** an in-process token bucket (`api/app/voting/ratelimit.py`), time-
  injectable so refill behavior is unit-tested without sleeping. A limit hit returns a
  friendly, specific message ("try again in about N seconds") with `Retry-After` set for
  well-behaved clients — never a raw `429`.

## Fallback not taken

PLAN.md's Phase 3 offered a smaller "community interest" thumbs-up fallback if time ran
short. It wasn't needed — full voting (with hidden-results windowing, duplicate
detection, rate limiting, and comments) shipped as specified.
