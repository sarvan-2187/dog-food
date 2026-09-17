"""Unit tests for the normalisation pipeline (PLAN.md section 8).

Pure-function tests: no client, no database. Section 8 names three cases that
must be covered -- a judge with only one assignment, a submission scored by only
one judge, and the full fixture dataset -- and each has a test below.
"""
import json
from pathlib import Path

import pytest

from app.scoring.normalization import (
    display_score,
    judge_z_scores,
    normalize_scores,
    normalized_table,
)


def test_normalisation_cancels_judge_harshness():
    """The point of the whole pipeline: a harsh judge and a generous judge who
    rank three submissions identically must contribute identical z-scores."""
    harsh = {101: 2.0, 102: 4.0, 103: 6.0}
    generous = {101: 8.0, 102: 9.0, 103: 10.0}
    z = judge_z_scores({1: harsh, 2: generous})
    assert z[1] == pytest.approx(z[2])

    z_bar = normalize_scores({1: harsh, 2: generous})
    assert z_bar[103] > z_bar[102] > z_bar[101]


def test_raw_mean_and_normalised_rankings_can_disagree():
    """A submission seen only by a generous judge can out-rank on raw mean while
    losing on normalised score. This is the case the whole pipeline exists for."""
    raw = {
        # A generous judge working in a narrow band at the top...
        1: {101: 9.0, 103: 9.1},
        # ...and a harsh judge using a much wider spread.
        2: {102: 5.0, 103: 1.0},
    }
    table = {int(r["submission_id"]): r for r in normalized_table(raw)}

    # On raw mean, 101 leads purely because only the generous judge saw it.
    assert table[101]["raw_mean"] > table[103]["raw_mean"] > table[102]["raw_mean"]

    # Normalised, that advantage disappears and the order fully inverts: within
    # their own judge's spread, 101 was the *weaker* of the two they saw.
    assert table[102]["z_bar"] > table[103]["z_bar"] > table[101]["z_bar"]
    assert table[102]["rank"] == 1 and table[101]["rank"] == 3


def test_single_assignment_judge_is_guarded_like_sigma_zero():
    """Section 8: a judge with one assignment must not divide by zero."""
    assert judge_z_scores({7: {101: 8.0}}) == {7: {101: 0.0}}


def test_judge_who_scores_everything_the_same_contributes_zero():
    assert judge_z_scores({7: {1: 5.0, 2: 5.0, 3: 5.0}}) == {7: {1: 0.0, 2: 0.0, 3: 0.0}}


def test_submission_scored_by_only_one_judge():
    z_bar = normalize_scores({1: {101: 2.0, 102: 6.0}, 2: {101: 9.0}})
    # 101 averages judge 1's -1.0 with judge 2's 0.0 (single assignment guard).
    assert z_bar[101] == pytest.approx(-0.5)
    assert z_bar[102] == pytest.approx(1.0)


def test_display_score_is_clamped_to_0_100():
    assert display_score(0.0) == 50.0
    assert display_score(1.0) == 60.0
    assert display_score(-1.0) == 40.0
    assert display_score(99.0) == 100.0
    assert display_score(-99.0) == 0.0


def test_empty_input_is_empty_output_not_a_crash():
    assert normalize_scores({}) == {}
    assert normalized_table({}) == []
    assert judge_z_scores({5: {}}) == {5: {}}


def test_ranking_is_deterministic_for_tied_scores():
    """Ties break by submission id, so repeated runs order identically."""
    raw = {1: {202: 5.0, 201: 5.0, 203: 5.0}}
    ranks = [r["submission_id"] for r in normalized_table(raw)]
    assert ranks == [201, 202, 203]
    assert ranks == [r["submission_id"] for r in normalized_table(raw)]


def test_full_fixture_dataset_normalises():
    """Section 8 asks for a test over the full fixture dataset. Build a realistic
    3-judge x 3-submission matrix over the seeded submissions and check the
    pipeline produces a complete, ranked, clamped table."""
    fixtures = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "submissions.json").read_text())
    submitted = [f for f in fixtures if f.get("status") == "submitted"]
    assert len(submitted) == 3, "fixture set changed; update this test deliberately"

    ids = [101, 102, 103]
    raw = {
        1: {ids[0]: 8.5, ids[1]: 6.0, ids[2]: 7.25},   # moderate
        2: {ids[0]: 4.0, ids[1]: 2.0, ids[2]: 3.5},    # harsh
        3: {ids[0]: 9.8, ids[1]: 9.0, ids[2]: 9.9},    # generous
    }
    table = normalized_table(raw)
    assert len(table) == 3
    assert [r["rank"] for r in table] == [1, 2, 3]
    assert all(r["judges"] == 3 for r in table)
    assert all(0.0 <= r["display"] <= 100.0 for r in table)
    # All three judges agree 102 is weakest, so it must rank last.
    assert table[-1]["submission_id"] == ids[1]
