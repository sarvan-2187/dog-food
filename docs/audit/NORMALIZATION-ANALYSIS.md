# Score normalization: tests and analysis (task 4)

Scope: `api/app/scoring/normalization.py` (the formula), the raw totals it is fed
(`scoring/router.py` `_weighted_total`, `_raw_by_judge`), the fixture seeder
(`seed.py`), and the organizer's `/results` and `results.csv`.

## Method

1. **Independent re-implementation.** `_reference()` in
   `api/tests/test_normalization_properties.py` computes z̄ straight from PLAN.md
   section 8 with no shared code. On 25 random panels and on the official DOGFOOD
   fixtures, the app agrees with it to 1e-12 (random) and 1e-6 (fixtures, after the
   6-decimal rounding of the output).
2. **Properties** that must hold for JUDGING.md's claims to be true, each a test:
   - every judge's z-scores have mean 0 and population stddev 1;
   - an affine change to one judge (`a·x + b`, `a > 0`: a harsher or more lenient
     judge) leaves every z̄ unchanged;
   - a judge with no spread, including one who scored a single project, contributes
     exactly 0;
   - relabelling judges or reordering input changes nothing;
   - one judge scoring everything ranks exactly as their raw totals;
   - display is `clamp(50 + 10·z̄, 0, 100)`, monotone, and ranking uses z̄: two
     entries both clamped at 100 keep their order.
3. **End to end.** The fixtures are seeded into a test database exactly as
   `docker compose up` does, and the live `GET /api/events/{id}/results` and
   `results.csv` are compared row by row with the reference (40 rows, ranks 1-40,
   z̄ within 1e-6, display = clamp(50 + 10·z̄)).
4. The pre-existing unit tests in `test_scoring.py` (single-assignment judge,
   single-judge submission, harsh vs lenient disagreement, deterministic ties,
   empty input). One of them, `test_full_fixture_dataset_normalises`, failed outside
   Docker because it only looked for fixtures at the container path; it now finds
   them in a plain checkout too.

## Findings

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| N1 | The formula is implemented correctly: population stddev, σ = 0 guard, z̄ over the judges who scored the entry, display clamp, deterministic tie-break by id. | - | Verified |
| N2 | Float noise cannot manufacture a spread. Raw totals are rounded to 6 decimals and `statistics.pstdev` is exact on equal inputs, so a judge whose totals are equal gets σ exactly 0. | - | Verified (`test_rounded_equal_totals_are_exact_ties`) |
| N3 | **The fixture seeder rounded equal weights to 0.3333/0.3333/0.3334.** A 5/4/3 then totalled 3.9999 against 4/4/4's 4.0, so genuinely equal raw means stopped being ties. The normalized ranking was unaffected (z̄ moved by at most 0.00024 and no rank changed), but the raw ranks in JUDGING.md's worked table were ordered by the rounding: Iron Switch and Salt Ledger are tied at 4.33, not 2nd and 1st. On a judge who gave near-flat scores, the same artifact could turn a 1e-4 difference into z = ±1. | Medium (documentation accuracy; latent ranking risk) | Fixed: exact 1/n weights in `seed.py`; JUDGING.md table corrected with tie-aware raw ranks |
| N4 | A submitted entry that no judge has scored does not appear in `/results` at all, rather than as a row with 0 judges. | Low | Documented; the judge progress dashboard and the assignment coverage warnings already show unscored work |
| N5 | A judge's scores carry weight only once they have scored at least two projects with different totals. | By design | Already documented in JUDGING.md ("The trade-off") |

## The full fixture table

Weights exactly 1/3 each; raw rank is tie-aware (`=`). Only 5 of 40 projects keep
their raw rank and the largest move is 21 places (Dry Harbour, 31st to 10th).

| Normalized rank | Raw rank | Move | Project | Judges | Raw mean | z̄ | Display |
|---|---|---|---|---|---|---|---|
| 1 | =1 | 0 | Iron Switch | 3 | 4.33 | +1.232 | 62.3 |
| 2 | =6 | +4 | Slow Trail | 3 | 4.00 | +0.918 | 59.2 |
| 3 | =1 | −2 | Salt Ledger | 4 | 4.33 | +0.867 | 58.7 |
| 4 | 5 | +1 | Salt Loom | 4 | 4.08 | +0.768 | 57.7 |
| 5 | =6 | +1 | Salt Kiln | 3 | 4.00 | +0.688 | 56.9 |
| 6 | 4 | −2 | Dry Relay | 3 | 4.11 | +0.609 | 56.1 |
| 7 | 3 | −4 | Still Beacon | 2 | 4.17 | +0.595 | 56.0 |
| 8 | =19 | +11 | Paper Anchor | 2 | 3.50 | +0.324 | 53.2 |
| 9 | =23 | +14 | Glass Signal | 3 | 3.44 | +0.288 | 52.9 |
| 10 | =29 | +19 | Dry Harbour | 6 | 3.33 | +0.263 | 52.6 |
| 11 | 8 | −3 | Copper Kiln | 3 | 3.89 | +0.229 | 52.3 |
| 12 | =10 | −2 | Green Switch | 3 | 3.78 | +0.179 | 51.8 |
| 13 | =15 | +2 | Small Loom | 3 | 3.56 | +0.174 | 51.7 |
| 14 | 9 | −5 | North Drift | 5 | 3.80 | +0.156 | 51.6 |
| 15 | =12 | −3 | Copper Orbit | 2 | 3.67 | +0.134 | 51.3 |
| 16 | =15 | −1 | Small Meadow | 3 | 3.56 | +0.107 | 51.1 |
| 17 | =15 | −2 | Salt Ferry | 3 | 3.56 | +0.098 | 51.0 |
| 18 | =15 | −3 | Hollow Signal | 3 | 3.56 | +0.080 | 50.8 |
| 19 | =12 | −7 | Salt Drift | 3 | 3.67 | +0.068 | 50.7 |
| 20 | =23 | +3 | Open Beacon | 3 | 3.44 | +0.056 | 50.6 |
| 21 | =23 | +2 | Flat Thread | 3 | 3.44 | +0.052 | 50.5 |
| 22 | =10 | −12 | Deep Beacon | 3 | 3.78 | +0.032 | 50.3 |
| 23 | =19 | −4 | Glass Beacon | 2 | 3.50 | +0.000 | 50.0 |
| 24 | =19 | −5 | Open Kiln | 2 | 3.50 | -0.001 | 50.0 |
| 25 | =29 | +4 | Flat Relay | 2 | 3.33 | -0.052 | 49.5 |
| 26 | 28 | +2 | Green Lantern | 5 | 3.40 | -0.062 | 49.4 |
| 27 | 22 | −5 | Warm Beacon | 5 | 3.47 | -0.106 | 48.9 |
| 28 | =33 | +5 | Amber Hours | 3 | 3.22 | -0.202 | 48.0 |
| 29 | =23 | −6 | Loud Ledger | 3 | 3.44 | -0.218 | 47.8 |
| 30 | =12 | −18 | Small Relay | 2 | 3.67 | -0.238 | 47.6 |
| 31 | =29 | −2 | Deep Compass | 3 | 3.33 | -0.261 | 47.4 |
| 32 | =35 | +3 | Paper Harbour | 3 | 3.11 | -0.343 | 46.6 |
| 33 | =29 | −4 | Quiet Anchor | 3 | 3.33 | -0.663 | 43.4 |
| 34 | =33 | −1 | Paper Thread | 3 | 3.22 | -0.674 | 43.3 |
| 35 | =35 | 0 | Dry Bridge | 3 | 3.11 | -0.792 | 42.1 |
| 36 | =35 | −1 | Dry Compass | 3 | 3.11 | -0.807 | 41.9 |
| 37 | =23 | −14 | Flat Meadow | 3 | 3.44 | -0.890 | 41.1 |
| 38 | 38 | 0 | Slow Loom | 2 | 3.00 | -0.970 | 40.3 |
| 39 | =39 | 0 | Slow Quarry | 3 | 2.89 | -1.119 | 38.8 |
| 40 | =39 | −1 | North Compass | 3 | 2.89 | -1.388 | 36.1 |
