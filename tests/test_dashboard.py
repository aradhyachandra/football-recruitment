"""Dashboard: the pure functions behind app/streamlit_app.py on hand-made data, the Kante default against
the saved R4 lists (needs data/processed/), and the app itself with streamlit's AppTest."""
import copy
import json

import pandas as pd
import pytest

from recruit import config, dashboard as dash, run_r4
from tests.test_run_r4 import CFG, METRICS_CFG, TARGET, make_inputs

ROOT = config.ROOT
APP = ROOT / "app" / "streamlit_app.py"
PROCESSED = ROOT / "data" / "processed"
REAL_CFG = config.load("similarity")


# ---------- pure functions on the hand-made pool (tests/test_run_r4.py) ----------

def test_normalise_weights():
    assert dash.normalise_weights({"a": 2, "b": 1, "c": 1}) == {"a": 0.5, "b": 0.25, "c": 0.25}
    with pytest.raises(ValueError):
        dash.normalise_weights({"a": 0, "b": 0})


def test_explore_with_defaults_is_the_r4_analysis():
    players, season, _ = make_inputs()
    target_teams = players.set_index("player_id").loc[TARGET, "team_ids"]
    res = dash.explore(players, season, CFG, METRICS_CFG, TARGET)
    r4 = run_r4.analyse(players, season, None, CFG, METRICS_CFG, with_stability=False)
    assert res["top_similar"] == r4["top_similar"]
    assert res["shortlist"] == r4["shortlist"]
    assert res["frontier"] == r4["frontier"]
    pd.testing.assert_series_equal(res["table"]["similarity"], r4["table"]["similarity"])
    assert target_teams == [22]  # so "exclude the selected player's clubs" equals the config rule here


def test_explore_config_changes_only_what_is_asked():
    players, _, _ = make_inputs()
    row = players.set_index("player_id").loc[202]
    cfg = dash.explore_config(CFG, 202, row["role"], row["team_ids"],
                              group_weights={"ball_winning": 1, "progression": 1, "passing_security": 0,
                                             "attacking_output": 0},
                              budget_cap_eur=3e6, age_range=(22, 30))
    assert cfg["pool"]["target_statsbomb_player_id"] == 202
    assert [t["statsbomb_team_id"] for t in cfg["constraints"]["exclude_teams"]] == [1]
    assert {g["name"]: g["weight"] for g in cfg["groups"]} == {"ball_winning": 0.5, "progression": 0.5,
                                                              "passing_security": 0.0, "attacking_output": 0.0}
    assert (cfg["constraints"]["budget_cap_eur"], cfg["constraints"]["age_min"], cfg["constraints"]["age_max"]) == (3e6, 22, 30)
    assert CFG["pool"]["target_statsbomb_player_id"] == TARGET  # base config untouched
    assert cfg["standardisation"] == CFG["standardisation"] and cfg["value_score"] == CFG["value_score"]


def test_explore_other_player_and_sliders():
    players, season, _ = make_inputs()
    res = dash.explore(players, season, CFG, METRICS_CFG, 202, budget_cap_eur=2.5e6, age_range=(20, 28))
    t = res["table"]
    assert bool(t.loc[202, "is_target"]) and 202 not in res["top_similar"]
    assert TARGET in t.index and TARGET in res["top_similar"]  # Kante-like target is now a candidate
    shortlist = t.loc[res["shortlist"]]
    assert (shortlist["market_value_eur"] <= 2.5e6).all() and shortlist["age"].between(20, 28).all()
    assert 205 not in res["shortlist"]  # club 1 is the selected player's own club: excluded


def test_list_tables_columns_and_flags():
    players, season, _ = make_inputs()
    res = dash.explore(players, season, CFG, METRICS_CFG, TARGET)
    sim_t = dash.similar_players(res)
    assert list(sim_t["Player"]) == [res["table"].loc[i, "name"] for i in res["top_similar"]]
    for col in ["Club", "League", "Age", "Market value (EUR m)", "Valued on", "Stale valuation", "Similarity"]:
        assert col in sim_t.columns
    by_name = sim_t.set_index("Player")
    assert by_name.loc["P207", "Market value (EUR m)"] is None or pd.isna(by_name.loc["P207", "Market value (EUR m)"])
    val_t = dash.value_shortlist(res)
    assert list(val_t["Player"]) == [res["table"].loc[i, "name"] for i in res["shortlist"]]
    assert list(val_t["Value rank"]) == list(range(1, len(val_t) + 1))
    stale = dash.value_shortlist(dash.explore(players, season, CFG, METRICS_CFG, TARGET, budget_cap_eur=4e6))
    assert stale.set_index("Player").loc["P205", "Stale valuation"] == "yes"


def test_percentile_profile():
    players, season, _ = make_inputs()
    res = dash.explore(players, season, CFG, METRICS_CFG, TARGET)
    prof = dash.percentile_profile(res, CFG, METRICS_CFG)
    keys = CFG["percentiles"]["key_metrics"]
    assert len(prof) == len(keys)
    labels = {m["name"]: m["label"] for m in METRICS_CFG["metrics"] + METRICS_CFG["ratios"]}
    assert list(prof["Metric"]) == [labels[k] for k in keys]
    assert "Pass completion" in list(prof["Metric"])  # ratios carry labels too
    t = res["table"]
    assert prof["Percentile"].iloc[0] == pytest.approx(100 * t.loc[TARGET, f"pct_{keys[0]}"])
    assert prof["Pool median"].iloc[0] == pytest.approx(t[f"value_{keys[0]}"].median())


def test_selectable_players_respects_minutes_threshold():
    players, _, _ = make_inputs()
    sel = dash.selectable_players(players, 900)
    assert 209 not in set(sel["player_id"]) and TARGET in set(sel["player_id"])
    assert sel["label"].is_unique


def test_robust_core_and_case_scatter_from_results():
    r = dash.load_results(ROOT)
    core = dash.robust_core_table(r["r5"])
    assert len(core) == len(r["r5"]["robust_core"])
    rec = [p["name"] for p in r["r5"]["recommendation"]]
    assert list(core.loc[core["Recommendation"] != "", "Player"]) == rec
    pts = dash.case_scatter_points(r["r4"], None)
    sl = pts[pts["Group"] == "Shortlist"]
    assert list(sl["Player"]) == [e["name"] for e in r["r4"]["shortlist"]]
    assert set(pts.loc[pts["On frontier"], "Player"]) == {e["name"] for e in r["r4"]["frontier"]}
    prof = dash.case_profile(r["r2"])
    assert len(prof) == len(r["r2"]["departing_player"]["profile"])


# ---------- Kante with default settings reproduces the saved R4 lists exactly ----------

@pytest.mark.skipif(not (PROCESSED / "r3" / "r3_player_values.parquet").exists(),
                    reason="needs data/processed/ (run R1-R3 first)")
def test_kante_defaults_reproduce_r4_lists_exactly():
    r4 = json.loads((ROOT / "results" / "r4_shortlist.json").read_text(encoding="utf-8"))
    players, season = dash.load_inputs(PROCESSED, config.load("scope"))
    target = REAL_CFG["pool"]["target_statsbomb_player_id"]
    res = dash.explore(players, season, REAL_CFG, config.load("metrics"), target)
    ids = lambda key: [e["statsbomb_player_id"] for e in r4[key]]  # noqa: E731
    assert res["top_similar"] == ids("top_similar")
    assert res["shortlist"] == ids("shortlist")
    assert res["frontier"] == ids("frontier")
    t = res["table"]
    for e in r4["shortlist"] + r4["top_similar"]:
        row = t.loc[e["statsbomb_player_id"]]
        assert round(float(row["similarity"]), 2) == e["similarity"]
        assert row["club"] == e["club"] and row["league"] == e["league"]
    for e in r4["shortlist"]:
        assert round(float(t.loc[e["statsbomb_player_id"], "value_score"]), 2) == e["value_score"]
    shown = dash.value_shortlist(res)
    assert list(shown["Player"]) == [e["name"] for e in r4["shortlist"]]


# ---------- the app (streamlit AppTest) ----------

def test_app_runs_without_processed_data(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv(config.load("publication")["dashboard"]["processed_dir_env"], str(tmp_path))
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception
    assert len(at.tabs) == 2
    text = " ".join(str(x.value) for x in list(at.markdown) + list(at.caption) + list(at.info))
    assert "similar profile under stated assumptions" in text.lower()
    assert "StatsBomb" in text and "transfermarkt-datasets" in text
    assert "run_r1" in text  # Explore view explains how to build data/processed/


@pytest.mark.skipif(not (PROCESSED / "r3" / "r3_player_values.parquet").exists(),
                    reason="needs data/processed/ (run R1-R3 first)")
def test_app_explore_kante_defaults_and_sliders():
    from streamlit.testing.v1 import AppTest

    r4 = json.loads((ROOT / "results" / "r4_shortlist.json").read_text(encoding="utf-8"))
    at = AppTest.from_file(str(APP), default_timeout=180).run()
    assert not at.exception
    frames = [df.value for df in at.dataframe]
    names = [list(f["Player"]) for f in frames if "Player" in f.columns]
    assert [e["name"] for e in r4["shortlist"]] in names
    assert [e["name"] for e in r4["top_similar"]] in names
    at.slider(key="budget").set_value(5_000_000).run()
    assert not at.exception
    capped = [df.value for df in at.dataframe if "Value rank" in df.value.columns][-1]
    assert (capped["Market value (EUR m)"] <= 5).all()


def test_dashboard_wording_rules():
    text = APP.read_text(encoding="utf-8").lower() + (ROOT / "src" / "recruit" / "dashboard.py").read_text(encoding="utf-8").lower()
    for banned in ["would succeed", "proven", "guarantee", "will succeed"]:
        assert banned not in text
