"""Per-judge z-score normalisation (PLAN.md section 8).

    mu_j    = mean of judge j's raw totals across their assigned submissions
    sigma_j = population stddev of judge j's raw totals
    z_{j,i} = (x_{j,i} - mu_j) / sigma_j      # sigma_j == 0 -> z = 0 for that judge
    z_bar_i = mean of z_{j,i} over judges j who scored submission i
    display_i = clamp(50 + 10 * z_bar_i, 0, 100)   # display only

z_bar_i stays the ranking value; display_i exists so a human sees a familiar
0-100 number. A judge with a single assignment has sigma == 0 and is handled by
the same guard as a judge who gave everyone the same score: they contribute 0,
meaning "no information about relative ordering", rather than a divide-by-zero.

Pure: no DB access, no imports from the rest of the app.
"""
from __future__ import annotations

from statistics import fmean, pstdev

RawScores = dict[int, dict[int, float]]  # judge_id -> {submission_id: raw_total}


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
        if sigma == 0:
            z_by_judge[judge_id] = {sid: 0.0 for sid in by_submission}
        else:
            z_by_judge[judge_id] = {sid: (x - mu) / sigma for sid, x in by_submission.items()}
    return z_by_judge


def normalize_scores(raw_scores_by_judge: RawScores) -> dict[int, float]:
    """submission_id -> z_bar_i, the ranking value."""
    z_by_judge = judge_z_scores(raw_scores_by_judge)
    collected: dict[int, list[float]] = {}
    for by_submission in z_by_judge.values():
        for submission_id, z in by_submission.items():
            collected.setdefault(submission_id, []).append(z)
    return {sid: fmean(zs) for sid, zs in collected.items() if zs}


def display_score(z_bar: float) -> float:
    """clamp(50 + 10 * z_bar, 0, 100). For UI display only -- never for ranking."""
    return max(0.0, min(100.0, 50 + 10 * z_bar))


def normalized_table(raw_scores_by_judge: RawScores) -> list[dict[str, float | int]]:
    """Ranked rows for the results endpoint and the CSV export.

    Ties break by submission id so repeated runs order identically.
    """
    z_bars = normalize_scores(raw_scores_by_judge)
    raw_mean: dict[int, list[float]] = {}
    informative: dict[int, int] = {}
    for by_submission in raw_scores_by_judge.values():
        # Same test as judge_z_scores: a judge with no spread carries no
        # ordering information and contributes z = 0.
        has_spread = len(by_submission) > 1 and pstdev(by_submission.values()) != 0
        for submission_id, x in by_submission.items():
            raw_mean.setdefault(submission_id, []).append(x)
            informative[submission_id] = informative.get(submission_id, 0) + has_spread

    rows = [
        {
            "submission_id": sid,
            "judges": len(raw_mean.get(sid, [])),
            "informative_judges": informative.get(sid, 0),
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
