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

**How judges join.** Through a single-use, expiring invitation that an organizer issues
for one event (`api/app/judging/invites.py`). Redeeming it adds the judge to that event's
panel only. Judges can't sign themselves up: self-service judge signup would let anyone
give themselves access to every score.

## Assignment algorithm

Implemented in `api/app/judging/assignment.py` as a pure, DB-free function:

```python
assign_judges(submissions, judges, team_memberships, k, *,
              existing=(), extra_conflicts=(), judge_tracks={}) -> list[JudgeAssignment]
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
4. **Idempotent, and it only fills gaps.** Re-running the assignment for an event that
   already has assignments does not create duplicates — the unique constraint on
   `(submission_id, judge_id)` is the hard guard, and the endpoint reports that nothing was
   left to do. Since Phase 10.7, existing assignments count toward each submission's `k`
   and toward each judge's load. So after a judge is removed, a re-run tops each
   submission back up to `k`, never past it. With nothing assigned yet, the result is
   identical to before.
5. **Only this event's judges (Phase 10.1).** The pool is the event's panel
   (`event_judges`), never every judge account on the platform.
6. **Declared conflicts (Phase 10.7).** A judge's `judge_conflicts` rows are added to the
   conflict set, so a submission they stepped back from is never handed back to them.
7. **Only after submissions close (Phase 10.3).** Assignment and scoring are refused
   before the event's `end_at`, so every score is of the version that was actually
   submitted. A judge's list only shows assignments from events whose judging has opened.
8. **Track judges (DOGFOOD T2: "a track judge must never see another track").** An
   organizer can give any judge on the panel one of the event's tracks, from the Judging
   progress card (`PUT /api/events/{id}/judges/{user_id}/track`, stored in
   `event_judges.track`). No track means the judge takes any track. The rule is one
   function, `outside_track()` in `assignment.py`:
   - a track judge is only ever given entries in exactly their track;
   - an entry in a track is offered to that track's judges first, then to untracked
     judges to reach `k` (the sort key is `(not a track judge, load, judge id)`, still
     total, so the run stays deterministic);
   - an entry with no track, or a track nobody judges, goes to untracked judges only. If
     there are not enough of them the entry is left short and listed in the coverage
     warnings. It is never handed to another track's judge.
   - A judge given a track after assignment keeps any entry they already **scored** in
     another track (a real judgement, like a removed judge's scores). Their **unscored**
     assignments outside the track are deleted at the start of the next assignment run,
     and the run refills those gaps.

   Assignment is not the only guard. `assert_in_track()` in `event_judges.py` runs on the
   score sheet, score submission and score read for every assignment, so a cross-track row
   that somehow exists (left from before the track was set, or written by hand) still gets
   a 403. The judge dashboard and `GET /api/judges/me/scores` leave such rows out, so a
   track judge never sees another track's entry anywhere.

### Award suggestions (Phase 10.6)

Each prize in `prize_config` gets a suggested winner from the normalised standings:
- A prize whose label names one of the event's tracks ("Best Developer Tool" ↔
  "Developer Tools") suggests that track's top-ranked project.
- Every other prize takes the next-ranked project not already suggested, in the order the
  prizes are configured.

Suggestions only pre-fill the picker: the organizer confirms every award. Awards follow
the same visibility rule as standings (`may_see_results`).

## Normalization

Implemented in `api/app/scoring/normalization.py` as a pure function:

```python
normalize_scores(raw_scores_by_judge) -> dict[submission_id, float]
```

```
mu_j    = mean of judge j's raw totals across their assigned submissions
sigma_j = population stddev of judge j's raw totals
judge j is INFORMATIVE when sigma_j > 1e-9 * max(1, |mu_j|)   # scored 2+ entries, not all equal
z_{j,i} = (x_{j,i} - mu_j) / sigma_j                        # informative judges only
z_bar_i = mean of z_{j,i} over the informative judges who scored i
          (0 if none did: "no evidence either way")
display_i = clamp(50 + 10 * z_bar_i, 0, 100)  # for UI display only; keep z_bar_i as the ranking value
```

This cancels out a judge's individual harshness or leniency. A judge who scores everything
low still ranks submissions correctly relative to each other, because it's their own mean
and spread doing the normalizing, not an absolute scale. `display_i` is cosmetic (a 0–100
number a human reads); `z_bar_i` is what actually determines rank. The full analysis,
measured on the official fixtures, is in
[`docs/NORMALIZATION-ANALYSIS.md`](docs/NORMALIZATION-ANALYSIS.md).

**How the raw total is formed.** Section 8 specifies normalization over "raw totals"
without saying how a raw total comes from rubric criteria. It is

```
raw_total = ( sum_c w_c * v_c / max_c ) / ( sum_c w_c ) * M        M = the largest max_score
```

Each value counts as a fraction of its own criterion's maximum before it is weighted, so a
weight means what the organizer set. With Technical scored 0–10 at 70% and Presentation
scored 0–100 at 30%, a plain `sum(w × v)` would give Presentation about 81% of the total,
just because its numbers are bigger (fixed 2026-09-29; test
`test_weighted_total_respects_weights_across_different_max_scores`). When every criterion
shares one `max_score` and the weights add to 1, which is true of every rubric the fixtures
ship, the formula is exactly `sum(w × v)`. The total stays on the familiar 0–`max_score`
scale, so "7.8 out of 10" still means something in the CSV export.

### Zero-information judges

A judge with a single score, or one who gave everything the same score, has σ = 0. Their
marks carry no information about *relative* order. They are **left out of z̄**, not averaged
in as a 0.

Until 2026-09-29 they were averaged in as a 0. That looks neutral, but it isn't. It shrinks
every other judge's signal for that project by a factor that depends only on how many
uninformative judges the project happened to draw. Two projects with identical informative
evidence could land on different ranks. On the fixtures, 3 of 30 judges are uninformative,
and removing the dilution moves 12 projects by 1–2 places (Small Relay from 30th to 32nd,
Dry Harbour from 10th to 9th). The top 8 are unchanged. The test
`test_an_uninformative_judge_does_not_change_a_projects_rank` pins the new behavior.

σ is compared against a small relative tolerance rather than exactly 0, so float noise in a
weighted total (`0.1 × 3` against `0.3`) can't turn identical marks into z = ±1
(`test_float_noise_is_not_mistaken_for_spread`).

### Partial data: normalization while judging is under way

Normalization is **recomputed on every read** from whatever scores exist. It is never cached
or frozen. So standings are live during judging, and they only settle once every assigned
judge has scored. Each result row says how complete it is:

- `judges` is the number of scores in;
- `assigned_judges` is the number of judges assigned to the project;
- `informative_judges` is how many of those scores actually moved z̄.

`judges < assigned_judges` means the row is still provisional. The results CSV carries all
three columns. Results stay hidden from everyone but organizers until the reveal time
(below), so nobody outside the organizing team ever sees provisional standings. The judging
progress card says who is behind.

Edge cases, each with a dedicated unit test in `api/tests/test_scoring.py`:
- A judge with only one assignment → uninformative, left out of z̄, never a division error.
- A submission scored by only one informative judge → takes that judge's z.
- A submission scored only by uninformative judges → z̄ = 0, `informative_judges = 0`.
- A dataset of judges with different harshness → the raw-mean ranking and the
  normalized ranking genuinely disagree, which is the point of normalizing at all.

### Worked on the official DOGFOOD fixtures

The fixture event (`sample-hack-2026`) has 40 submissions, 30 judges and 123 scores,
with 2 to 6 judges per project. Its criteria are `functionality`, `quality` and
`innovation`, on a 1–5 scale and weighted equally. The table is the unedited
`GET /api/events/10/export/results.csv` from a fresh `docker compose up`. *Raw rank*
orders the same rows by plain raw mean (ties by id). *Move* is raw rank minus normalized
rank, so a positive number means normalizing moved the project up.

| Normalized rank | Raw rank | Move | Project | Judges (informative) | Raw mean | z̄ | Display |
|---|---|---|---|---|---|---|---|
| 1 | 2 | +1 | Iron Switch | 3 (3) | 4.33 | +1.232 | 62.3 |
| 2 | 7 | +5 | Slow Trail | 3 (3) | 4.00 | +0.918 | 59.2 |
| 3 | 1 | −2 | Salt Ledger | 4 (4) | 4.33 | +0.867 | 58.7 |
| 4 | 5 | +1 | Salt Loom | 4 (4) | 4.08 | +0.768 | 57.7 |
| 5 | 6 | +1 | Salt Kiln | 3 (3) | 4.00 | +0.688 | 56.9 |
| 6 | 4 | −2 | Dry Relay | 3 (3) | 4.11 | +0.609 | 56.1 |
| 7 | 3 | −4 | Still Beacon | 2 (2) | 4.17 | +0.595 | 56.0 |
| 8 | 19 | +11 | Paper Anchor | 2 (2) | 3.50 | +0.324 | 53.2 |
| 9 | 31 | +22 | Dry Harbour | 6 (5) | 3.33 | +0.316 | 53.2 |
| 10 | 27 | +17 | Glass Signal | 3 (3) | 3.44 | +0.288 | 52.9 |

Only 2 of the 40 projects keep their raw rank, and the largest move is 22 places. Two of the
fixture's deliberate awkward cases explain the biggest moves:

- **Small Relay drops from 12th to 32nd.** It was scored by `jdg_07`, the judge who gave
  every project 4/4/4, and by `jdg_29`. `jdg_07` has σ = 0, so their 4.0 says nothing
  about *this* project and is left out. `jdg_29`'s 3.33 is below that judge's own average
  (about 3.5), so the project's z̄ is that judge's −0.476, even though its raw mean of 3.67
  looks above average.
- **Dry Harbour rises from 31st to 9th.** Its raw mean is pulled down by `jdg_01`'s
  2/2/2, but that is the only project `jdg_01` scored. With one score there is no spread,
  and nothing shows whether 2.0 is harsh or just that judge's normal. So `jdg_01` is left
  out, and the other five judges, each measured against their own average, place it above
  average. Dry Harbour is also the fixture's duplicate submission (`prj_07` and `prj_41`).
  Merging the two gives it 6 judges (README).

**The trade-off.** A judge's scores only count once that judge has scored more than one
project. That is deliberate: without a spread there is no scale to normalize against. It is
also the cost of this method. An organizer who wants every judge to count should assign at
least two projects each. The assignment run's `judges_per_submission` makes that the normal
case. The rows' `informative_judges` column shows where it didn't happen.

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
- A track judge gets a 403 on the sheet, score submission and score read for any entry
  outside their track, even with an assignment row for it (assignment rule 8 above).

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

## Disqualification and the standings

An organizer can rule a submitted entry ineligible (`POST /api/submissions/{id}/eligibility`,
a reason is required and shown to the team). One predicate, `in_competition()` in
`submissions/models.py`, is what the gallery, voting, assignment and awards all filter on,
so a disqualified entry leaves every one of them together rather than one list at a time.

For the standings, `_raw_by_judge` drops the entry's scores **before** normalization, so
every judge's `mu_j` and `sigma_j` are recomputed as if it had never been judged. Leaving
the scores in and only hiding the row would have been wrong: a judge who gave the
disqualified entry a very low score would keep that score in their mean, and every other
project they scored would look better than it was. Disqualifying deletes only the entry's
*unscored* assignments; scores stay in the database, so reinstating puts the entry and
its reviews straight back and the normalization reruns on the next read.

## The judging deadline is soft

`Event.judging_deadline` is shown to judges (a countdown, then "Overdue") and to the
organizer's progress view, and reminder emails name it. It never locks scoring. A hard
lock would leave some projects with fewer reviews, and normalization can't repair a
missing review; a late one is still a real review. So a score saved after the deadline
simply records `late: true` in its audit entry, and the organizer decides what to do
about it.

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
