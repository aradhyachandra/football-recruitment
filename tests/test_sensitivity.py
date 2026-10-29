"""R5 on hand-made data: config changes, the new value scores and stale rule, Dirichlet draws, the
scenario runner on the R4 test pool, robustness counts, the robust core and the recommendation rule."""
import copy

import numpy as np
import pandas as pd
import pytest

from recruit import config, run_r4, sensitivity as sens
from recruit import similarity as sim
from tests.test_run_r4 import CFG, METRICS_CFG, TARGET, make_inputs

SENS = config.load("sensitivity")


# ---------- applying one change ----------

def test_apply_changes_dotted_and_group_weights():
    out = sens.apply_changes(CFG, {"pool.min_minutes": 600, "value_score.similarity_weight": 0.5,
                                   "value_score.price_weight": 0.5})
    assert out["pool"]["min_minutes"] == 600 and out["value_score"]["similarity_weight"] == 0.5
    assert CFG["value_score"]["similarity_weight"] == 0.7                 # base untouched
    w = {"ball_winning": 0.25, "progression": 0.25, "passing_security": 0.25, "attacking_output": 0.25}
    out = sens.apply_changes(CFG, {"group_weights": w})
    assert {g["name"]: g["weight"] for g in out["groups"]} == w


def test_apply_changes_rejects_unknown_paths_and_groups():
    with pytest.raises(KeyError):
        sens.apply_changes(CFG, {"pool.min_minutez": 600})
    with pytest.raises(KeyError):
        sens.apply_changes(CFG, {"group_weights": {"ball_winning": 1.0}})   # every group must be given


def test_config_scenarios_change_one_thing_and_apply_to_the_real_base():
    base = config.load("similarity")
    ids = [s["id"] for s in SENS["scenarios"]]
    assert len(ids) == len(set(ids)) and ids[0] == "base"
    for s in SENS["scenarios"]:
        assert s["reason"] and s["kind"] in {"base", "value", "weights", "pool", "metrics", "constraints"}
        cfg = sens.apply_changes(base, s["changes"])
        assert np.isclose(sum(g["weight"] for g in cfg["groups"]), 1.0)
        assert np.isclose(cfg["value_score"]["similarity_weight"] + cfg["value_score"]["price_weight"], 1.0)
    assert sum(not s["changes"] for s in SENS["scenarios"]) == 1


def test_config_fingerprint_changes_with_any_setting():
    a = sens.config_fingerprint(CFG)
    assert a == sens.config_fingerprint(copy.deepcopy(CFG)) and len(a) == 64
    assert a != sens.config_fingerprint(sens.apply_changes(CFG, {"pool.min_minutes": 901}))


# ---------- new value scores and the stale rule ----------

def test_minmax_log_value_score():
    s = pd.Series([90.0, 80.0, 70.0], index=list("ABC"))
    p = pd.Series([4e6, 2e6, 1e6], index=list("ABC"))
    v = sim.value_score_minmax_log(s, p, 0.5, 0.5)
    assert v["A"] == pytest.approx(50.0) and v["C"] == pytest.approx(50.0)
    assert v["B"] == pytest.approx(100 * (0.5 * 0.5 + 0.5 * 0.5))       # 2m is halfway on the log scale
    assert sim.value_score_minmax_log(s, p, 1.0, 0.0).tolist() == pytest.approx([100.0, 50.0, 0.0])


def test_stale_rule_exclude_and_unknown():
    df = pd.DataFrame({"market_value_eur": [5, 5], "age": [25, 25], "team_ids": [[1], [1]],
                       "valuation_stale": [True, False]}, index=list("AB"))
    cons = {"budget_cap_eur": 10, "age_min": 20, "age_max": 28, "exclude_teams": [], "stale_valuations": "exclude"}
    assert sim.constraint_mask(df, cons)["eligible"].tolist() == [False, True]
    assert sim.constraint_mask(df, cons | {"stale_valuations": "flag"})["eligible"].tolist() == [True, True]
    with pytest.raises(ValueError):
        sim.constraint_mask(df, cons | {"stale_valuations": "drop"})


def test_value_scales_in_analyse():
    inputs = make_inputs()
    only = run_r4.analyse(*inputs, sens.apply_changes(CFG, {"value_score.scale": "similarity_only"}),
                          METRICS_CFG, with_stability=False)
    t = only["table"]
    elig = t[t["eligible"] == True]                                       # noqa: E712
    assert only["shortlist"] == list(elig.sort_values("similarity", ascending=False).index[:3])
    assert only["stability"] is None
    mm = run_r4.analyse(*inputs, sens.apply_changes(CFG, {"value_score.scale": "minmax_log_value_across_pool"}),
                        METRICS_CFG, with_stability=False)
    assert mm["table"]["value_score"].dropna().between(0, 100).all()
    with pytest.raises(ValueError):
        run_r4.analyse(*inputs, sens.apply_changes(CFG, {"value_score.scale": "nope"}), METRICS_CFG)


# ---------- Dirichlet draws ----------

def test_dirichlet_draws_reproducible_and_valid():
    a = sens.dirichlet_group_weights(CFG, 50, seed=7, concentration=40)
    b = sens.dirichlet_group_weights(CFG, 50, seed=7, concentration=40)
    c = sens.dirichlet_group_weights(CFG, 50, seed=8, concentration=40)
    assert a == b and a != c and len(a) == 50
    names = [g["name"] for g in CFG["groups"]]
    assert all(list(d) == names and np.isclose(sum(d.values()), 1.0) and min(d.values()) > 0 for d in a)
    mean = {n: np.mean([d[n] for d in sens.dirichlet_group_weights(CFG, 4000, 1, 40)]) for n in names}
    assert all(abs(mean[g["name"]] - g["weight"]) < 0.01 for g in CFG["groups"])   # centred on the base


# ---------- robustness counts on a hand-made rank table ----------

def _frames():
    # three scenarios, top_n = 2, top_k = 1. NaN = not eligible / not in the pool in that scenario.
    return {"s1": pd.DataFrame({"value_rank": [1, 2, 3, np.nan], "similarity": [80, 90, 70, 60.0]}, index=[1, 2, 3, 4]),
            "s2": pd.DataFrame({"value_rank": [2, 1, 3, 4], "similarity": [82, 88, 71, 61.0]}, index=[1, 2, 3, 4]),
            "s3": pd.DataFrame({"value_rank": [1, 3, 2, np.nan], "similarity": [84, 86, 72, np.nan]}, index=[1, 2, 3, 4])}


def test_robustness_counts():
    r = sens.robustness(_frames(), "value_rank", top_n=2, top_k=1)
    assert r.loc[1, "share_top_n"] == pytest.approx(1.0) and r.loc[1, "share_top_k"] == pytest.approx(2 / 3)
    assert r.loc[2, "share_top_n"] == pytest.approx(2 / 3) and r.loc[2, "share_top_k"] == pytest.approx(1 / 3)
    assert r.loc[3, "share_top_n"] == pytest.approx(1 / 3)
    assert (r.loc[2, "median_rank"], r.loc[2, "min_rank"], r.loc[2, "max_rank"]) == (2, 1, 3)
    assert r.loc[4, "ranked"] == 1 and r.loc[4, "scenarios"] == 3 and r.loc[4, "share_top_n"] == 0
    assert r.loc[1, "median_similarity"] == pytest.approx(82) and r.loc[4, "median_similarity"] == pytest.approx(60.5)


def test_robust_core_and_recommendation():
    r = sens.robustness(_frames(), "value_rank", top_n=2, top_k=1)
    core = sens.robust_core(r, 2 / 3)
    assert core == [1, 2]
    picks = sens.recommend(r, core, count=3)
    assert [p["player_id"] for p in picks] == [1, 2, 3]
    assert [p["in_core"] for p in picks] == [True, True, False]           # fallback fills the third place


def test_recommendation_tie_broken_by_median_similarity():
    r = pd.DataFrame({"share_top_n": [1.0, 1.0, 0.9], "share_top_k": [0.5, 0.5, 0.9],
                      "median_similarity": [80.0, 85.0, 70.0]}, index=[1, 2, 3])
    assert [p["player_id"] for p in sens.recommend(r, [1, 2, 3], count=3)] == [3, 2, 1]


# ---------- the runner on the R4 hand-made pool ----------

SMALL = copy.deepcopy(SENS)
SMALL["random_weights"].update(draws=5)
SMALL["views"].update(top_n=3, top_k=1)


@pytest.fixture(scope="module")
def run():
    return sens.run(*make_inputs(), CFG, SMALL, METRICS_CFG)


def test_runner_base_matches_r4(run):
    r4 = run_r4.analyse(*make_inputs(), CFG, METRICS_CFG)
    base = run["named"]["base"]
    assert list(base["value_rank"].dropna().sort_values().index[:3]) == r4["shortlist"]
    assert TARGET not in base.index


def test_runner_scenarios_and_draws(run):
    assert list(run["named"]) == [s["id"] for s in SENS["scenarios"]]
    assert len(run["draws"]) == 5 and len(run["draw_weights"]) == 5
    assert len(set(run["fingerprints"].values())) == len(run["fingerprints"])   # every scenario differs
    # stale player 205 is eligible in the base and not when stale valuations are excluded
    assert not np.isnan(run["named"]["base"].loc[205, "value_rank"])
    assert np.isnan(run["named"]["stale_excluded"].loc[205, "value_rank"])
    # budget EUR 5m keeps 202 (exactly 5m); 15m lets 203 (12m) in
    assert not np.isnan(run["named"]["budget_15m"].loc[203, "value_rank"])
    assert np.isnan(run["named"]["base"].loc[203, "value_rank"])
    # age 18-30 lets 206 (18) in
    assert not np.isnan(run["named"]["age_18_30"].loc[206, "value_rank"])
    # minutes 1,500: every hand-made player has 2,000, pool unchanged; similarity unchanged by value scenarios
    pd.testing.assert_series_equal(run["named"]["value_weight_0.9"]["similarity"], run["named"]["base"]["similarity"])
    assert not run["named"]["weights_equal"]["similarity"].equals(run["named"]["base"]["similarity"])


def test_runner_draws_reproducible(run):
    again = sens.run(*make_inputs(), CFG, SMALL, METRICS_CFG)
    assert again["draw_weights"] == run["draw_weights"]
    for a, b in zip(again["draws"], run["draws"]):
        pd.testing.assert_frame_equal(a, b)


def test_summarise(run):
    s = sens.summarise(run, CFG, SMALL)
    assert s["named"]["scenarios"] == len(SENS["scenarios"]) and s["draws"]["draws"] == 5
    ids = {c["statsbomb_player_id"] for c in s["candidates"]}
    assert TARGET not in ids
    rec = s["recommendation"]
    assert len(rec) == 3 and len({p["player_id"] for p in rec}) == 3
    c = s["candidates"][0]
    assert set(c) >= {"value_named", "value_draws", "similarity_named", "similarity_draws", "in_core"}
    assert 0 <= c["value_named"]["share_top_n"] <= 1
    assert s["similarity_view_scenarios"] == [x["id"] for x in SENS["scenarios"]
                                              if x["kind"] in SENS["views"]["similarity_view_kinds"]]


def test_robustness_rank_quantiles_from_the_argument():
    frames = [pd.DataFrame({"value_rank": [float(r)], "similarity": [80.0]}, index=[1]) for r in range(1, 102)]
    r = sens.robustness(frames, "value_rank", top_n=10, top_k=3, quantiles=(0.1, 0.9))
    assert (r.loc[1, "p05_rank"], r.loc[1, "p95_rank"]) == (11, 91)
