"""Per-judge z-score normalisation (PLAN.md section 8).

    mu_j    = mean of judge j's raw totals across their assigned submissions
    sigma_j = population stddev of judge j's raw totals
    z_{j,i} = (x_{j,i} - mu_j) / sigma_j      # sigma_j == 0 -> z = 0 for that judge
    z_bar_i = mean of z_{j,i} over the INFORMATIVE judges j who scored i
              (sigma_j > 0); 0 if submission i has no informative judge
    display_i = clamp(50 + 10 * z_bar_i, 0, 100)   # display only

z_bar_i stays the ranking value; display_i exists so a human sees a familiar
0-100 number. A judge with a single assignment has sigma == 0, like a judge who
gave everyone the same score: neither says anything about relative order.

Such a judge is left out of z_bar entirely - not averaged in as a 0. Averaging
a 0 in is not neutral: it halves the signal of a project's one informative
judge, so a project's rank would depend on how many uninformative judges it
happened to draw (JUDGING.md, "Zero-information judges"). sigma is compared
against a tolerance, not exactly 0, so float noise in a weighted total (e.g.
4.000000000000001 vs 4.0) can't turn identical marks into z = +/-1.

Pure: no DB access, no imports from the rest of the app.
"""
from __future__ import annotations

from statistics import fmean, pstdev

RawScores = dict[int, dict[int, float]]  # judge_id -> {submission_id: raw_total}

# Relative tolerance for "this judge has no spread". Raw totals are rounded to
# 6 places when stored, so anything below this is rounding, not judgement.
SPREAD_TOLERANCE = 1e-9


def _has_spread(totals: list[float]) -> bool:
    if len(totals) < 2:
        return False
    mu = fmean(totals)
    return pstdev(totals) > SPREAD_TOLERANCE * max(1.0, abs(mu))


def informative_judges(raw_scores_by_judge: RawScores) -> set[int]:
    """Judges whose scores carry ordering information (sigma_j > 0)."""
    return {j for j, by_sub in raw_scores_by_judge.items() if _has_spread(list(by_sub.values()))}


def judge_z_scores(raw_scores_by_judge: RawScores) -> dict[int, dict[int, float]]:
    """judge_id -> {submission_id: z}. A judge with no spread contributes zeros."""
    z_by_judge: dict[int, dict[int, float]] = {}
    for judge_id, by_submission in raw_scores_by_judge.items():
        if not by_submission:
            z_by_judge[judge_id] = {}
            continue
        totals = list(by_submission.values())
        mu = fmean(totals)
        sigma = pstdev(totals)  # population stddev; 0 for a single assignment
        if not _has_spread(totals):
            z_by_judge[judge_id] = {sid: 0.0 for sid in by_submission}
        else:
            z_by_judge[judge_id] = {sid: (x - mu) / sigma for sid, x in by_submission.items()}
    return z_by_judge


def normalize_scores(raw_scores_by_judge: RawScores) -> dict[int, float]:
    """submission_id -> z_bar_i, the ranking value. Every scored submission gets
    a value; one with no informative judge gets 0.0 ("no evidence either way")."""
    z_by_judge = judge_z_scores(raw_scores_by_judge)
    informative = informative_judges(raw_scores_by_judge)
    collected: dict[int, list[float]] = {}
    for judge_id, by_submission in z_by_judge.items():
        for submission_id, z in by_submission.items():
            bucket = collected.setdefault(submission_id, [])
            if judge_id in informative:
                bucket.append(z)
    return {sid: fmean(zs) if zs else 0.0 for sid, zs in collected.items()}


def display_score(z_bar: float) -> float:
    """clamp(50 + 10 * z_bar, 0, 100). For UI display only -- never for ranking."""
    return max(0.0, min(100.0, 50 + 10 * z_bar))


def normalized_table(raw_scores_by_judge: RawScores) -> list[dict[str, float | int]]:
    """Ranked rows for the results endpoint and the CSV export.

    Ties break by submission id so repeated runs order identically.
    """
    z_bars = normalize_scores(raw_scores_by_judge)
    informative = informative_judges(raw_scores_by_judge)
    raw_mean: dict[int, list[float]] = {}
    counted: dict[int, int] = {}
    for judge_id, by_submission in raw_scores_by_judge.items():
        for submission_id, x in by_submission.items():
            raw_mean.setdefault(submission_id, []).append(x)
            counted[submission_id] = counted.get(submission_id, 0) + (judge_id in informative)

    rows = [
        {
            "submission_id": sid,
            "judges": len(raw_mean.get(sid, [])),
            # How many of those judges actually moved z_bar (sigma_j > 0).
            "informative_judges": counted.get(sid, 0),
            "raw_mean": round(fmean(raw_mean[sid]), 4) if raw_mean.get(sid) else 0.0,
            "z_bar": round(z_bar, 6),
            "display": round(display_score(z_bar), 2),
        }
        for sid, z_bar in z_bars.items()
    ]
    rows.sort(key=lambda r: (-r["z_bar"], r["submission_id"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows
