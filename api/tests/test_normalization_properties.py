"""Properties of the z-score normalization (task 4), checked on random data and
on the official DOGFOOD fixtures, against an independent re-implementation.

What must hold for PLAN.md section 8 / JUDGING.md to be true:

- each judge's z-scores have mean 0 and population stddev 1 (or are all 0);
- a judge's harshness or leniency (x -> a*x + b, a > 0) changes nothing;
- a judge with no spread contributes exactly 0;
- relabelling judges or reordering input changes nothing;
- one judge scoring everything ranks exactly as their raw totals do;
- display is 50 + 10*z_bar clamped to [0, 100] and never used for ranking.
"""
import json
import math
import random
from pathlib import Path

import pytest

from app.scoring.normalization import display_score, judge_z_scores, normalize_scores, normalized_table


def _reference(raw: dict) -> dict:
    """Straight from JUDGING.md's formula, sharing no code with the app:
    uninformative judges (sigma ~ 0) are left out of the mean, and an entry
    seen only by them sits at 0."""
    zs: dict = {}
    for scores in raw.values():
        xs = list(scores.values())
        if not xs:
            continue
        mu = sum(xs) / len(xs)
        sigma = math.sqrt(sum((x - mu) ** 2 for x in xs) / len(xs))
        for sid, x in scores.items():
            zs.setdefault(sid, [])
            if sigma > 1e-9 * max(1.0, abs(mu)):
                zs[sid].append((x - mu) / sigma)
    return {sid: sum(v) / len(v) if v else 0.0 for sid, v in zs.items()}


def _random_panel(rng: random.Random, judges: int = 8, subs: int = 20, per_judge: int = 6) -> dict:
    raw = {}
    for j in range(1, judges + 1):
        chosen = rng.sample(range(100, 100 + subs), per_judge)
        raw[j] = {s: round(rng.uniform(0, 10), 6) for s in chosen}
    return raw


@pytest.mark.parametrize("seed", range(25))
def test_matches_independent_reference(seed):
    raw = _random_panel(random.Random(seed))
    got = normalize_scores(raw)
    want = _reference(raw)
    assert set(got) == set(want)
    for sid in want:
        assert got[sid] == pytest.approx(want[sid], abs=1e-12)


@pytest.mark.parametrize("seed", range(10))
def test_each_judge_is_standardised(seed):
    raw = _random_panel(random.Random(seed))
    for judge, zs in judge_z_scores(raw).items():
        values = list(zs.values())
        assert sum(values) / len(values) == pytest.approx(0.0, abs=1e-9)
        assert math.sqrt(sum(v * v for v in values) / len(values)) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("scale,shift", [(0.5, 0.0), (2.0, -3.0), (0.1, 7.0), (10.0, 100.0)])
def test_harsh_or_lenient_judge_changes_nothing(scale, shift):
    raw = _random_panel(random.Random(7))
    before = normalize_scores(raw)
    transformed = {j: dict(s) for j, s in raw.items()}
    transformed[3] = {sid: scale * x + shift for sid, x in raw[3].items()}
    after = normalize_scores(transformed)
    for sid in before:
        assert after[sid] == pytest.approx(before[sid], abs=1e-9)


def test_flat_judge_contributes_exactly_zero():
    # Judge 1 gave everything a 4: left out of the mean, not averaged in as 0.
    raw = {1: {1: 4.0, 2: 4.0, 3: 4.0}, 2: {1: 2.0, 2: 6.0}}
    assert judge_z_scores(raw)[1] == {1: 0.0, 2: 0.0, 3: 0.0}
    z = normalize_scores(raw)
    assert z[3] == 0.0
    assert z[1] == pytest.approx(-1.0) and z[2] == pytest.approx(1.0)


def test_rounded_equal_totals_are_exact_ties():
    """Raw totals are rounded to 6 d.p. before they get here, so a judge whose
    totals are equal has sigma exactly 0 - float noise never becomes a spread."""
    from app.scoring.router import _weighted_total

    third = [{"key": k, "weight": 1 / 3} for k in ("a", "b", "c")]
    totals = [_weighted_total(third, v) for v in ({"a": 5, "b": 4, "c": 3}, {"a": 4, "b": 4, "c": 4},
                                                  {"a": 3, "b": 5, "c": 4})]
    assert len(set(totals)) == 1
    raw = {1: dict(zip((1, 2, 3), totals))}
    assert judge_z_scores(raw)[1] == {1: 0.0, 2: 0.0, 3: 0.0}


def test_rounded_weights_break_ties_that_exact_weights_keep():
    """Why the fixture seeder now uses exact 1/n weights."""
    from app.scoring.router import _weighted_total

    rounded = [{"key": "a", "weight": 0.3333}, {"key": "b", "weight": 0.3333}, {"key": "c", "weight": 0.3334}]
    assert _weighted_total(rounded, {"a": 5, "b": 4, "c": 3}) != _weighted_total(rounded, {"a": 4, "b": 4, "c": 4})


def test_judge_labels_and_input_order_do_not_matter():
    raw = _random_panel(random.Random(3))
    relabelled = {j * 1000: dict(reversed(list(s.items()))) for j, s in reversed(list(raw.items()))}
    a, b = normalize_scores(raw), normalize_scores(relabelled)
    for sid in a:
        assert b[sid] == pytest.approx(a[sid], abs=1e-12)


def test_single_judge_ranks_as_raw():
    rng = random.Random(11)
    raw = {1: {sid: rng.uniform(0, 10) for sid in range(50)}}
    table = normalized_table(raw)
    assert [r["submission_id"] for r in table] == sorted(raw[1], key=lambda s: (-raw[1][s], s))


def test_display_is_monotone_and_clamped():
    zs = [-10, -5.0001, -5, -1, 0, 0.5, 5, 5.0001, 10]
    shown = [display_score(z) for z in zs]
    assert shown == sorted(shown)
    assert min(shown) == 0.0 and max(shown) == 100.0
    assert display_score(0.5) == 55.0


def test_ranking_uses_z_bar_not_display():
    """Two entries beyond the clamp both display 100 but keep their order."""
    # One outlier among n equal scores has z = sqrt(n - 1): 5.10 and 6.0 here.
    raw = {
        1: {**{sid: 0.0 for sid in range(1, 27)}, 27: 100.0},
        2: {**{sid: 0.0 for sid in range(100, 136)}, 136: 100.0},
    }
    table = normalized_table(raw)
    assert table[0]["display"] == table[1]["display"] == 100.0
    assert table[0]["z_bar"] > table[1]["z_bar"]
    assert [table[0]["submission_id"], table[1]["submission_id"]] == [136, 27]


# --- the official DOGFOOD fixtures ------------------------------------------

def _dogfood_fixture() -> dict:
    here = Path(__file__).resolve()
    for p in (here.parents[2] / "fixtures.json", here.parents[1] / "fixtures" / "dogfood.json"):
        if p.exists():
            return json.loads(p.read_text())
    pytest.skip("DOGFOOD fixtures.json not found")


def _dogfood_raw() -> tuple[dict, dict]:
    """Mirrors seed._seed_dogfood: duplicates fold into the team's first
    project, a judge's second score of the same project is dropped, and the
    three criteria are weighted exactly 1/3."""
    from app.scoring.router import _weighted_total

    data = _dogfood_fixture()
    first_of_team: dict = {}
    project: dict = {}
    titles: dict = {}
    for row in data["projects"]:
        pid = first_of_team.setdefault(row["team"], row["id"])
        project[row["id"]] = pid
        titles.setdefault(pid, row["title"])
    keys = list(dict.fromkeys(k for s in data["scores"] for k in s["criteria"]))
    criteria = [{"key": k, "weight": 1 / len(keys)} for k in keys]
    raw: dict = {}
    for row in data["scores"]:
        pid = project[row["project"]]
        raw.setdefault(row["judge"], {}).setdefault(pid, _weighted_total(criteria, row["criteria"]))
    return raw, titles


def test_dogfood_fixture_shape():
    raw, titles = _dogfood_raw()
    assert len(raw) == 30
    assert sum(len(s) for s in raw.values()) == 123
    assert len({sid for s in raw.values() for sid in s}) == 40


def test_dogfood_fixture_matches_reference_and_judging_md():
    raw, titles = _dogfood_raw()
    table = normalized_table(raw)
    ref = _reference(raw)
    for row in table:
        assert row["z_bar"] == pytest.approx(ref[row["submission_id"]], abs=1e-6)
    by_title = {titles[r["submission_id"]]: r for r in table}
    # The worked example in JUDGING.md.
    assert table[0]["submission_id"] == next(k for k, v in titles.items() if v == "Iron Switch")
    assert by_title["Iron Switch"]["z_bar"] == pytest.approx(1.232, abs=5e-4)
    assert by_title["Iron Switch"]["display"] == pytest.approx(62.3, abs=0.05)
    assert by_title["Small Relay"]["rank"] == 32  # 30 before uninformative judges were left out
    assert by_title["Dry Harbour"]["rank"] == 9  # 10 before uninformative judges were left out
    assert by_title["Dry Harbour"]["judges"] == 6


def test_dogfood_flat_and_single_score_judges_contribute_zero():
    raw, _ = _dogfood_raw()
    z = judge_z_scores(raw)
    flat = [j for j, s in raw.items() if len(set(s.values())) == 1]
    assert "jdg_07" in flat and "jdg_01" in flat
    for j in flat:
        assert set(z[j].values()) == {0.0}


def test_dogfood_results_endpoint_end_to_end(client, session):
    """Seed the fixtures into the database the way `docker compose up` does, then
    check the organizer's /results and results.csv against the reference."""
    import csv
    import io

    from sqlmodel import select

    from app.auth.models import Role, User
    from app.auth.session import create_session_token
    from app.events.models import Event
    from app.seed import DOGFOOD_EVENT_SLUG, _seed_dogfood

    here = Path(__file__).resolve()
    path = next((p for p in (here.parents[2] / "fixtures.json", here.parents[1] / "fixtures" / "dogfood.json")
                 if p.exists()), None)
    if path is None:
        pytest.skip("DOGFOOD fixtures.json not found")
    organizer = User(email="norm-org@example.com", name="Org", role=Role.organizer, password_hash="x")
    session.add(organizer)
    session.commit()
    _seed_dogfood(session, path)
    session.commit()
    event = session.exec(select(Event).where(Event.slug == DOGFOOD_EVENT_SLUG)).one()

    client.cookies.set("session", create_session_token(organizer.id, organizer.session_version))
    rows = client.get(f"/api/events/{event.id}/results").json()
    raw, titles = _dogfood_raw()
    ref = _reference(raw)
    by_title = {titles[k]: v for k, v in ref.items()}
    assert len(rows) == 40
    assert [r["rank"] for r in rows] == list(range(1, 41))
    for r in rows:
        assert r["z_bar"] == pytest.approx(by_title[r["submission_title"]], abs=1e-6)
        assert r["display"] == pytest.approx(max(0, min(100, 50 + 10 * r["z_bar"])), abs=0.01)
    assert rows[0]["submission_title"] == "Iron Switch"

    csv_rows = list(csv.DictReader(io.StringIO(client.get(f"/api/events/{event.id}/export/results.csv").text)))
    assert [(c["submission_title"], float(c["z_bar"])) for c in csv_rows] == [
        (r["submission_title"], r["z_bar"]) for r in rows
    ]
