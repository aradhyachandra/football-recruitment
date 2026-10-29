"""R4 on hand-made data: the split-half SQL, the whole analysis on a small pool (target never a
candidate, constraints, unpriced and stale players, frontier, shortlist order, stability), the doc and
the figures."""
import copy
import hashlib

import numpy as np
import pandas as pd
import pytest

from recruit import config, load, r4_figures, run_r4
from recruit import similarity as sim

CFG = copy.deepcopy(config.load("similarity"))
CFG["pool"]["min_minutes"] = 900
CFG["stability"]["min_minutes_per_half"] = 300
CFG["outputs"].update(shortlist_size=3, top_similar_size=3, figure_top_profiles=2)
METRICS_CFG = config.load("metrics")
METRICS = list(sim.metric_weights(CFG)) + [m["name"] for m in CFG["excluded_metrics"]]
ADJ = run_r4.adjusted_metrics(CFG, METRICS_CFG)
TARGET = CFG["pool"]["target_statsbomb_player_id"]


# ---------- split-half SQL ----------

def test_half_profiles_sql():
    con = load.connect(":memory:", "1GB", 1)
    con.execute("CREATE TABLE sb_matches AS SELECT * FROM (VALUES (1, DATE '2015-09-01'), (2, DATE '2015-12-31'),"
                " (3, DATE '2016-01-01'), (4, DATE '2016-03-01')) t(match_id, match_date)")
    rows = []
    for match_id, minutes, tackles, adj, done, tried in [(1, 90, 2, 1.5, 30, 40), (2, 45, 1, 1.0, 10, 10),
                                                        (3, 90, 0, 0.0, 20, 25), (4, 60, 3, 4.0, 15, 25)]:
        rows += [(match_id, 7, minutes, "tackles_won", True, tackles, adj),
                 (match_id, 7, minutes, "passes_completed", False, done, None),
                 (match_id, 7, minutes, "passes_attempted", False, tried, None)]
    con.execute("CREATE TABLE r2_player_match (match_id BIGINT, player_id BIGINT, minutes DOUBLE, metric VARCHAR,"
                " possession_adjusted BOOLEAN, raw DOUBLE, adjusted DOUBLE)")
    con.executemany("INSERT INTO r2_player_match VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    con.execute(run_r4.config.SQL_DIR.joinpath("r4_half_profiles.sql").read_text(), {"split_date": "2016-01-01"})
    out = {(h, m): (mins, v, vp) for h, mins, m, v, vp in
           con.execute("SELECT half, minutes, metric, value, value_padj FROM r4_half_profiles").fetchall()}
    assert out[(1, "tackles_won")] == pytest.approx((135, 3 / 135 * 90, 2.5 / 135 * 90))
    assert out[(2, "tackles_won")] == pytest.approx((150, 3 / 150 * 90, 4 / 150 * 90))   # 1 Jan is half 2
    assert out[(1, "passes_completed")][2] is None
    assert out[(1, "pass_completion")][1] == pytest.approx(40 / 50)
    assert out[(2, "pass_completion")][1] == pytest.approx(35 / 50)
    assert not any(m == "passes_attempted" for _, m in out)


# ---------- a hand-made pool ----------
# Target T (id = config target) at Leicester. Candidates, with profile = target x factor + small fixed noise:
#   201 clone  x1.00, Leicester (excluded by team)    202 near  x0.95, EUR 5m
#   203 near2  x0.93, EUR 12m (over the cap)           204 half  x0.50, EUR 1m
#   205 mid    x0.80, EUR 3m, stale valuation          206 young x0.90, age 18 (too young)
#   207 nomatch x0.97, no price                        208 other x0.70, EUR 2m
#   209 low minutes (800) and 210 another role: not in the pool.

def _base():
    rng = np.random.RandomState(4)
    return {m: 1.0 + 3 * rng.rand() for m in METRICS}


SPEC = {TARGET: (1.00, 25, 20e6, False, [22]), 201: (1.00, 24, 4e6, False, [22]),
        202: (0.95, 24, 5e6, False, [1]), 203: (0.93, 26, 12e6, False, [2]), 204: (0.50, 23, 1e6, False, [3]),
        205: (0.80, 27, 3e6, True, [1]), 206: (0.90, 18, 2e6, False, [2]), 207: (0.97, 25, None, None, [3]),
        208: (0.70, 22, 2e6, False, [4]), 209: (0.99, 22, 1e6, False, [4]), 210: (0.99, 22, 1e6, False, [4])}


def _value(base, m, f, pid, half=0):
    noise = 0.002 * ((pid * 7 + len(m) * 3 + half * 5) % 5 - 2)
    return 0.5 + 0.4 * f + noise if m == "pass_completion" else base[m] * f + noise


def make_inputs():
    base = _base()
    players, season, halves = [], [], []
    for pid, (f, age, value, stale, teams) in SPEC.items():
        players.append({"player_id": pid, "name": f"P{pid}" if pid != TARGET else "Target", "club": f"Club{teams[0]}",
                        "team_ids": teams, "league": "L", "role": "Other" if pid == 210 else "Central midfielder",
                        "minutes": 800 if pid == 209 else 2000, "age": age, "market_value_eur": value,
                        "valuation_date": None if value is None else pd.Timestamp("2016-06-01"),
                        "valuation_stale": stale})
        for m in METRICS:
            v = _value(base, m, f, pid)
            season.append({"player_id": pid, "metric": m, "value": v * 1.1, "value_padj": v if m in ADJ else None})
            for h in (1, 2):
                vh = _value(base, m, f, pid, h)
                halves.append({"player_id": pid, "half": h, "minutes": 1000, "metric": m, "value": vh * 1.1,
                               "value_padj": vh if m in ADJ else None})
    return pd.DataFrame(players), pd.DataFrame(season), pd.DataFrame(halves)


@pytest.fixture(scope="module")
def res():
    return run_r4.analyse(*make_inputs(), CFG, METRICS_CFG)


def test_pool_and_target(res):
    t = res["table"]
    assert set(t.index) == {TARGET, *range(201, 209)}                  # 209 under minutes, 210 other role
    assert t.loc[TARGET, "similarity"] == pytest.approx(100.0) and t.loc[TARGET, "is_target"]
    for key in ("shortlist", "top_similar", "frontier"):
        assert TARGET not in res[key]
    assert res["counts"] == res["counts"] | {"pool": 9, "candidates": 8, "priced": 7, "unpriced": 1}


def test_adjusted_values_enter_for_defensive_metrics(res):
    t = res["table"]
    assert t.loc[202, "value_tackles_won"] == pytest.approx(_value(_base(), "tackles_won", 0.95, 202))
    assert t.loc[202, "value_shots"] == pytest.approx(1.1 * _value(_base(), "shots", 0.95, 202))


def test_similarity_follows_level(res):
    t = res["table"]
    assert t.loc[201, "similarity"] > t.loc[202, "similarity"] > t.loc[208, "similarity"] > t.loc[204, "similarity"]
    assert res["top_similar"] == [201, 207, 202]               # regardless of price, team or a missing value
    assert t.loc[204, "cosine"] < 1


def test_constraints_and_shortlist(res):
    t = res["table"]
    assert not t.loc[201, "eligible"] and not t.loc[201, "team_ok"]        # Leicester
    assert not t.loc[203, "within_budget"] and not t.loc[206, "age_ok"] and not t.loc[207, "within_budget"]
    assert set(t.index[t["eligible"] == True]) == {202, 204, 205, 208}     # noqa: E712
    assert res["shortlist"] == [202, 205, 208]
    assert res["counts"]["stale_eligible"] == 1


def test_frontier(res):
    # cheapest-first: 204 (1m) is the cheapest; 208/206 at 2m (206 more similar); 205 3m; 201 4m clone
    assert set(res["frontier"]) == {204, 206, 201}


def test_stability(res):
    st = res["stability"]
    assert st["players"] == 9 and st["target_qualifies"]
    assert st["top_k"][0]["chance"] == pytest.approx(1 / 9)
    assert 0 <= st["top_k"][0]["share"] <= st["top_k"][1]["share"] <= 1


def test_stability_minutes_per_half_filter():
    players, season, halves = make_inputs()
    halves.loc[(halves["player_id"] == 204) & (halves["half"] == 2), "minutes"] = 100
    out = run_r4.analyse(players, season, halves, CFG, METRICS_CFG)
    assert out["stability"]["players"] == 8 and pd.isna(out["table"].loc[204, "self_match_rank"])


def test_target_must_be_in_the_pool():
    players, season, halves = make_inputs()
    players.loc[players["player_id"] == TARGET, "minutes"] = 100
    with pytest.raises(ValueError, match="not in the"):
        run_r4.analyse(players, season, halves, CFG, METRICS_CFG)


def test_summary_doc_and_figures(res, tmp_path):
    s = run_r4.build_summary(res, CFG, "f" * 64)
    assert [e["statsbomb_player_id"] for e in s["shortlist"]] == [202, 205, 208]
    assert s["shortlist"][1]["valuation_stale"] is True
    assert set(s["shortlist"][0]) >= {"name", "club", "league", "age", "market_value_eur", "valuation_date",
                                      "valuation_stale", "similarity", "cosine", "percentiles", "value_score"}
    assert set(s["target"]["percentiles"]) == set(CFG["percentiles"]["key_metrics"])
    doc = run_r4.render({**s, "_groups": CFG["groups"]}, run_r4.TEMPLATE.read_text(encoding="utf-8"))
    assert "{{" not in doc and "P205 (stale value)" in doc and "StatsBomb" in doc
    files = r4_figures.draw(res, s, CFG, tmp_path / "docs" / "figures")
    assert all((tmp_path / f).stat().st_size > 10_000 for f in files)


def test_fingerprint_is_sha256_of_the_file(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text("a: 1\n")
    assert run_r4.fingerprint(p) == hashlib.sha256(b"a: 1\n").hexdigest()
