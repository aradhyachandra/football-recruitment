"""R4 maths on small hand-made profiles: weights, standardisation and clipping, distance and score,
cosine, percentile ranks, split-half self-match ranks, the frontier, constraints and the value score."""
import math

import numpy as np
import pandas as pd
import pytest

from recruit import similarity as sim

CFG = {
    "groups": [
        {"name": "def", "weight": 0.6, "metrics": [{"name": "a", "weight": 1.0}, {"name": "b", "weight": 0.5}]},
        {"name": "att", "weight": 0.4, "metrics": [{"name": "c", "weight": 1.0}]},
    ],
}


def test_metric_weights_normalise_inside_groups_and_add_to_one():
    w = sim.metric_weights(CFG)
    assert w == pytest.approx({"a": 0.4, "b": 0.2, "c": 0.4})
    assert sum(w.values()) == pytest.approx(1.0)
    assert sim.metric_groups(CFG) == {"a": "def", "b": "def", "c": "att"}


def test_metric_weights_reject_group_weights_not_adding_to_one():
    bad = {"groups": [{"name": "g", "weight": 0.5, "metrics": [{"name": "a", "weight": 1}]}]}
    with pytest.raises(ValueError, match="add up to 1"):
        sim.metric_weights(bad)


def test_profile_matrix_uses_adjusted_values_for_defensive_metrics_only():
    long = pd.DataFrame({"player_id": [1, 1, 2, 2], "metric": ["a", "c", "a", "c"],
                         "value": [5.0, 1.0, 3.0, 2.0], "value_padj": [4.0, None, 2.5, None]})
    X = sim.profile_matrix(long, ["a", "c"], adjusted={"a"})
    assert X.loc[1, "a"] == 4.0 and X.loc[2, "a"] == 2.5 and X.loc[1, "c"] == 1.0
    X_raw = sim.profile_matrix(long, ["a", "c"], adjusted=set())
    assert X_raw.loc[1, "a"] == 5.0


def test_profile_matrix_stops_on_a_missing_value():
    long = pd.DataFrame({"player_id": [1, 2], "metric": ["a", "a"], "value": [1.0, None], "value_padj": [None, None]})
    with pytest.raises(ValueError, match="missing"):
        sim.profile_matrix(long, ["a"], adjusted=set())


def test_standardise_population_z_scores():
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0]}, index=[10, 11, 12])
    Z, clipped = sim.standardise(X, clip=3.0, ddof=0)
    sd = math.sqrt(2 / 3)
    assert Z["a"].tolist() == pytest.approx([-1 / sd, 0.0, 1 / sd])
    assert not clipped.values.any()


def test_standardise_clips_extremes_and_reports_them():
    X = pd.DataFrame({"a": [0.0] * 19 + [100.0]})   # one outlier: z = sqrt(19) = 4.36
    Z, clipped = sim.standardise(X, clip=3.0)
    assert Z["a"].max() == 3.0 and clipped["a"].sum() == 1 and bool(clipped["a"].iloc[-1])


def test_standardise_constant_metric_stops():
    with pytest.raises(ValueError, match="no spread"):
        sim.standardise(pd.DataFrame({"a": [2.0, 2.0]}), clip=3.0)


def test_distance_score_and_cosine():
    w = {"a": 0.5, "c": 0.5}
    Z = pd.DataFrame({"a": [2.0, 2.0, 1.0, -2.0], "c": [1.0, 1.0, 0.5, -1.0]}, index=["T", "same", "half", "opp"])
    d = sim.distances(Z, "T", w)
    assert d["same"] == 0.0
    assert d["half"] == pytest.approx(math.sqrt(0.5 * 1 + 0.5 * 0.25))
    assert d["opp"] == pytest.approx(math.sqrt(0.5 * 16 + 0.5 * 4))
    s = sim.similarity_score(d, clip=3.0)
    assert s["same"] == 100.0 and s["half"] == pytest.approx(100 * (1 - d["half"] / 6))
    cos = sim.cosine(Z, "T", w)
    # half the output in the same proportions: same shape (cosine 1) but a lower similarity score
    assert cos["half"] == pytest.approx(1.0) and cos["opp"] == pytest.approx(-1.0)
    assert s["half"] < s["same"]


def test_score_is_zero_at_the_largest_possible_distance():
    w = {"a": 1.0}
    Z = pd.DataFrame({"a": [3.0, -3.0]}, index=["T", "far"])
    assert sim.similarity_score(sim.distances(Z, "T", w), clip=3.0)["far"] == pytest.approx(0.0)


def test_weights_change_who_is_closest():
    Z = pd.DataFrame({"a": [0.0, 1.0, 0.0], "c": [0.0, 0.0, 1.5]}, index=["T", "x", "y"])
    assert sim.distances(Z, "T", {"a": 0.9, "c": 0.1}).idxmin() == "T"
    d_def = sim.distances(Z, "T", {"a": 0.9, "c": 0.1}).drop("T")
    d_att = sim.distances(Z, "T", {"a": 0.1, "c": 0.9}).drop("T")
    assert d_def.idxmin() == "y" and d_att.idxmin() == "x"


def test_percent_rank_matches_duckdb_definition():
    s = pd.Series([3.0, 1.0, 2.0, 2.0])
    assert sim.percent_rank(s).tolist() == pytest.approx([1.0, 0.0, 1 / 3, 1 / 3])
    assert sim.percent_rank(pd.Series([5.0])).tolist() == [0.0]


def test_self_match_ranks():
    w = {"a": 0.5, "c": 0.5}
    first = pd.DataFrame({"a": [1.0, -1.0, 0.0], "c": [1.0, -1.0, 2.0]}, index=[1, 2, 3])
    # players 1 and 3 stay put; player 2 drifts so far that both others' second halves are closer
    second = pd.DataFrame({"a": [1.0, 0.0, 0.0], "c": [1.0, 3.0, 2.0]}, index=[1, 2, 3])
    ranks = sim.self_match_ranks(first, second, w)
    assert ranks.to_dict() == {1: 1, 2: 3, 3: 1}


def test_self_match_ranks_ties_count_against_the_player():
    w = {"a": 1.0}
    first = pd.DataFrame({"a": [0.0, 5.0]}, index=[1, 2])
    second = pd.DataFrame({"a": [1.0, -1.0]}, index=[1, 2])   # both second halves 1 away from player 1
    assert sim.self_match_ranks(first, second, w)[1] == 2


def test_self_match_ranks_need_the_same_players():
    with pytest.raises(ValueError, match="same players"):
        sim.self_match_ranks(pd.DataFrame({"a": [0.0]}, index=[1]), pd.DataFrame({"a": [0.0]}, index=[2]), {"a": 1})


def test_frontier_weak_dominance():
    df = pd.DataFrame({"similarity": [90, 80, 80, 70, 85, 60],
                       "market_value_eur": [10, 5, 5, 1, 12, 1]}, index=list("ABCDEF"))
    f = sim.frontier(df["similarity"], df["market_value_eur"])
    # A: nobody as similar and cheaper. B and C tie: neither dominates the other. D: cheapest at 70.
    # E dominated by A (more similar and cheaper). F dominated by D (same price, more similar).
    assert f.to_dict() == {"A": True, "B": True, "C": True, "D": True, "E": False, "F": False}


def test_constraints():
    cons = {"budget_cap_eur": 10, "age_min": 20, "age_max": 28,
            "exclude_teams": [{"statsbomb_team_id": 22}]}
    df = pd.DataFrame({"market_value_eur": [10, 11, 5, 5, 5, None], "age": [25, 25, 19, 29, 28, 25],
                       "team_ids": [[1], [1], [1], [1], [3, 22], [1]]}, index=list("ABCDEF"))
    m = sim.constraint_mask(df, cons)
    assert m["within_budget"].tolist() == [True, False, True, True, True, False]
    assert m["age_ok"].tolist() == [True, True, False, False, True, True]
    assert m["team_ok"].tolist() == [True, True, True, True, False, True]
    assert m["eligible"].tolist() == [True, False, False, False, False, False]


def test_value_score_ranks_similarity_first_and_breaks_ties_by_similarity():
    df = pd.DataFrame({"similarity": [90.0, 80.0, 70.0, 60.0],
                       "market_value_eur": [8, 4, 2, 1]}, index=list("ABCD"))
    v = sim.value_score(df["similarity"], df["market_value_eur"], 0.7, 0.3)
    # similarity percentiles 100, 66.7, 33.3, 0; cheapness percentiles 0, 33.3, 66.7, 100
    assert v.to_dict() == pytest.approx({"A": 70.0, "B": 56.667, "C": 43.333, "D": 30.0}, abs=1e-3)
    order = sim.rank_by_value(pd.DataFrame({"value_score": v, "similarity": df["similarity"]}))
    assert order == list("ABCD")
    tie = pd.DataFrame({"value_score": [50.0, 50.0], "similarity": [60.0, 70.0]}, index=["x", "y"])
    assert sim.rank_by_value(tie) == ["y", "x"]


def test_value_score_price_only_and_ties_share_rank():
    df = pd.DataFrame({"similarity": [1.0, 2.0, 3.0], "market_value_eur": [5, 5, 1]}, index=list("ABC"))
    v = sim.value_score(df["similarity"], df["market_value_eur"], 0.0, 1.0)
    assert v["C"] == pytest.approx(100.0) and v["A"] == v["B"] == pytest.approx(0.0)


def test_value_score_weights_must_add_to_one():
    with pytest.raises(ValueError, match="add up to 1"):
        sim.value_score(pd.Series([1.0]), pd.Series([1]), 0.5, 0.4)


def test_group_gaps():
    w = {"a": 0.4, "b": 0.2, "c": 0.4}
    groups = {"a": "def", "b": "def", "c": "att"}
    Z = pd.DataFrame({"a": [0.0, 1.0], "b": [0.0, 1.0], "c": [0.0, 2.0]}, index=["T", "x"])
    g = sim.group_gaps(Z, "T", w, groups)
    assert g.loc["x", "def"] == pytest.approx(1.0) and g.loc["x", "att"] == pytest.approx(2.0)
    # group gaps recombine into the distance
    d = sim.distances(Z, "T", w)["x"]
    assert d == pytest.approx(np.sqrt(0.6 * 1.0 ** 2 + 0.4 * 2.0 ** 2))
