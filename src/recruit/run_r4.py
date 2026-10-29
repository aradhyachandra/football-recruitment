"""R4: similarity to the departing player, split-half stability, value for money and the shortlist.

    python -m recruit.run_r4

Needs the DuckDB database built by R1-R3. Settings: config/similarity.yaml (its sha256 is saved with
the results). Writes per-player tables to data/processed/r4/ (gitignored); results/r4_shortlist.json
holds only the shortlist, the top-similar list, the frontier, the stability result and the config
fingerprint; figures go to docs/figures/ and docs/R4_shortlist.md is rendered from its template.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from recruit import config, flatten, load, report
from recruit import similarity as sim

ROOT = config.ROOT
CONFIG_FILE = config.CONFIG_DIR / "similarity.yaml"
SUMMARY = ROOT / "results" / "r4_shortlist.json"
TEMPLATE = ROOT / "docs" / "templates" / "R4_shortlist.md"
DOC = ROOT / "docs" / "R4_shortlist.md"
FIGURES = ROOT / "docs" / "figures"


def fingerprint(path: Path = CONFIG_FILE) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def adjusted_metrics(cfg: dict, metrics_cfg: dict) -> set[str]:
    if not cfg["possession_adjusted"]["use_adjusted_for_defensive"]:
        return set()
    return {m["name"] for m in metrics_cfg["metrics"] if m.get("possession_adjusted")}


def stability(pool_ids, half_long: pd.DataFrame, cfg: dict, metrics: list[str], adjusted: set[str],
              w: dict, target) -> tuple[dict, pd.Series]:
    st, std = cfg["stability"], cfg["standardisation"]
    mins = half_long.groupby(["player_id", "half"])["minutes"].first().unstack().reindex(columns=[1, 2])
    mins = mins[mins.index.isin(pool_ids)]
    ok = mins[(mins[1] >= st["min_minutes_per_half"]) & (mins[2] >= st["min_minutes_per_half"])].index
    halves = []
    for h in (1, 2):
        rows = half_long[(half_long["half"] == h) & half_long["player_id"].isin(ok)]
        halves.append(sim.standardise(sim.profile_matrix(rows, metrics, adjusted), std["clip"], std["ddof"])[0])
    ranks = sim.self_match_ranks(halves[0], halves[1], w)
    n = len(ranks)
    out = {"split_date": st["split_date"], "min_minutes_per_half": st["min_minutes_per_half"],
           "pool_players": len(pool_ids), "players": n,
           "top_k": [{"k": k, "players": int((ranks <= k).sum()), "share": float((ranks <= k).mean()),
                      "chance": k / n} for k in st["top_k"]],
           "median_rank": float(ranks.median()),
           "target_qualifies": bool(target in ranks.index),
           "target_rank": int(ranks[target]) if target in ranks.index else None}
    return out, ranks


def analyse(players: pd.DataFrame, season_long: pd.DataFrame, half_long: pd.DataFrame, cfg: dict,
            metrics_cfg: dict) -> dict:
    """players: one row per player_id with name, club, team_ids, league, role, minutes, age,
    market_value_eur, valuation_date, valuation_stale. season_long / half_long: R2 / r4_half_profiles rows.
    Returns the per-player table (pool) and the pieces of the summary."""
    w, groups = sim.metric_weights(cfg), sim.metric_groups(cfg)
    metrics = list(w)
    adjusted = adjusted_metrics(cfg, metrics_cfg)
    std, p = cfg["standardisation"], cfg["pool"]
    target = p["target_statsbomb_player_id"]
    pool = players[(players["role"] == p["role"]) & (players["minutes"] >= p["min_minutes"])].set_index("player_id")
    if target not in pool.index:
        raise ValueError(f"target {target} is not in the {p['role']} pool")

    rows = season_long[season_long["player_id"].isin(pool.index)]
    X = sim.profile_matrix(rows, metrics, adjusted)
    Z, clipped = sim.standardise(X, std["clip"], std["ddof"])
    d = sim.distances(Z, target, w)
    table = pool.copy()
    table["distance"] = d
    table["similarity"] = sim.similarity_score(d, std["clip"])
    table["cosine"] = sim.cosine(Z, target, w)
    table["clipped_values"] = clipped.sum(axis=1)
    for g, s in sim.group_gaps(Z, target, w, groups).items():
        table[f"gap_{g}"] = s
    context = [m["name"] for m in cfg["excluded_metrics"]]
    X_all = X.join(sim.profile_matrix(rows, context, adjusted))
    for m in X_all.columns:
        table[f"value_{m}"] = X_all[m]
        table[f"pct_{m}"] = sim.percent_rank(X_all[m])
    table["is_target"] = table.index == target

    cand = table.drop(index=target)
    priced = cand[cand["market_value_eur"].notna()]
    table["on_frontier"] = sim.frontier(priced["similarity"], priced["market_value_eur"])
    cons = sim.constraint_mask(cand, cfg["constraints"])
    for c in cons.columns:
        table[c] = cons[c]
    eligible = cand[cons["eligible"]]
    vc = cfg["value_score"]
    table["value_score"] = sim.value_score(eligible["similarity"], eligible["market_value_eur"],
                                           vc["similarity_weight"], vc["price_weight"])
    order = sim.rank_by_value(table.loc[eligible.index])
    table["value_rank"] = pd.Series(range(1, len(order) + 1), index=order)
    table["similarity_rank"] = cand["distance"].rank(method="min").astype(int)

    stab, ranks = stability(pool.index, half_long, cfg, metrics, adjusted, w, target)
    table["self_match_rank"] = ranks
    out = cfg["outputs"]
    return {
        "table": table, "weights": w, "adjusted": adjusted, "stability": stab,
        "shortlist": order[:out["shortlist_size"]],
        "top_similar": list(cand.sort_values(["distance"], kind="mergesort").index[:out["top_similar_size"]]),
        "frontier": list(table[table["on_frontier"] == True].sort_values("market_value_eur").index),  # noqa: E712
        "counts": {"pool": len(pool), "candidates": len(cand), "priced": len(priced),
                   "unpriced": len(cand) - len(priced), "eligible": len(eligible),
                   "stale_priced": int((priced["valuation_stale"] == True).sum()),
                   "stale_eligible": int((eligible["valuation_stale"] == True).sum()),
                   "excluded_budget": int((~cons["within_budget"] & cand["market_value_eur"].notna()).sum()),
                   "excluded_age": int((~cons["age_ok"]).sum()), "excluded_team": int((~cons["team_ok"]).sum()),
                   "clipped_values_pool": int(clipped.values.sum()),
                   "clipped_values_target": int(clipped.loc[target].sum())},
    }


def _num(x):
    return None if pd.isna(x) else (int(x) if float(x).is_integer() else float(x))


def entry(table: pd.DataFrame, pid, key_metrics: list[str], groups: list[str]) -> dict:
    r = table.loc[pid]
    e = {"statsbomb_player_id": int(pid), "name": r["name"], "club": r["club"], "league": r["league"],
         "age": _num(r["age"]), "minutes": round(float(r["minutes"])),
         "market_value_eur": _num(r["market_value_eur"]),
         "valuation_date": None if pd.isna(r["valuation_date"]) else str(r["valuation_date"])[:10],
         "valuation_stale": None if pd.isna(r["valuation_stale"]) else bool(r["valuation_stale"]),
         "similarity": round(float(r["similarity"]), 2), "cosine": round(float(r["cosine"]), 3),
         "distance": round(float(r["distance"]), 3),
         "group_gaps": {g: round(float(r[f"gap_{g}"]), 3) for g in groups},
         "percentiles": {m: round(float(r[f"pct_{m}"]), 3) for m in key_metrics}}
    if not r["is_target"]:
        e |= {"similarity_rank": int(r["similarity_rank"]), "on_frontier": bool(r["on_frontier"] == True),  # noqa: E712
              "meets_constraints": bool(r["eligible"] == True)}  # noqa: E712
        if not pd.isna(r["value_score"]):
            e |= {"value_score": round(float(r["value_score"]), 2), "value_rank": int(r["value_rank"])}
    if not pd.isna(r.get("self_match_rank")):
        e["self_match_rank"] = int(r["self_match_rank"])
    return e


def build_summary(res: dict, cfg: dict, fp: str) -> dict:
    t = res["table"]
    groups = [g["name"] for g in cfg["groups"]]
    keys = cfg["percentiles"]["key_metrics"]
    target = cfg["pool"]["target_statsbomb_player_id"]
    c = cfg["constraints"]
    return {
        "config_file": "config/similarity.yaml", "config_sha256": fp,
        "pool": {"role": cfg["pool"]["role"], "min_minutes": cfg["pool"]["min_minutes"], **res["counts"]},
        "settings": {"group_weights": {g["name"]: g["weight"] for g in cfg["groups"]},
                     "metric_weights": {m: round(v, 4) for m, v in res["weights"].items()},
                     "possession_adjusted_metrics": sorted(res["adjusted"] & set(res["weights"])),
                     "clip": cfg["standardisation"]["clip"],
                     "value_weights": {"similarity": cfg["value_score"]["similarity_weight"],
                                       "price": cfg["value_score"]["price_weight"]},
                     "budget_cap_eur": c["budget_cap_eur"], "age_min": c["age_min"], "age_max": c["age_max"],
                     "excluded_teams": [x["name"] for x in c["exclude_teams"]]},
        "target": entry(t, target, keys, groups),
        "shortlist": [entry(t, i, keys, groups) for i in res["shortlist"]],
        "top_similar": [entry(t, i, keys, groups) for i in res["top_similar"]],
        "frontier": [entry(t, i, keys, groups) for i in res["frontier"]],
        "stability": res["stability"],
    }


# ---------- reading the database ----------

def read_inputs(con, scope: dict, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    con.execute((config.SQL_DIR / "r4_half_profiles.sql").read_text(encoding="utf-8"),
                {"split_date": cfg["stability"]["split_date"]})
    leagues = {c["competition_id"]: c["name"] for c in scope["competitions"]}
    team_names = dict(con.execute("SELECT DISTINCT team_id, team_name FROM sb_lineup_players").fetchall())
    players = con.execute("""
        SELECT v.player_id, v.statsbomb_name AS name, v.minutes, v.role, v.main_competition_id, v.age,
               v.market_value_eur, v.valuation_date, v.valuation_stale,
               list_transform(p.teams, t -> t.team_id) AS team_ids
        FROM r3_player_values v JOIN r2_players p USING (player_id) ORDER BY v.player_id""").df()
    players["team_ids"] = players["team_ids"].map(list)
    players["club"] = players["team_ids"].map(lambda ids: " / ".join(team_names[i] for i in ids))
    players["league"] = players["main_competition_id"].map(leagues)
    season = con.execute("SELECT player_id, metric, value, value_padj FROM r2_player_season").df()
    halves = con.execute("SELECT * FROM r4_half_profiles").df()
    return players, season, halves


def check_halves(con) -> None:
    """Half totals must add up to the season: minutes for every player."""
    bad = con.execute("""
        WITH h AS (SELECT player_id, sum(minutes) AS m FROM
                   (SELECT DISTINCT player_id, half, minutes FROM r4_half_profiles) GROUP BY player_id)
        SELECT count(*) FROM h JOIN r2_players p USING (player_id) WHERE abs(h.m - p.minutes) > 1e-6""").fetchone()[0]
    if bad:
        raise ValueError(f"half minutes do not add up to season minutes for {bad} players")


def save_table(table: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    t = table.reset_index().copy()
    t["team_ids"] = t["team_ids"].map(lambda x: [int(i) for i in x])
    t.to_parquet(out_dir / "r4_similarity.parquet", index=False)


# ---------- doc ----------

def _m(x):
    return None if x is None else x / 1e6


def render(s: dict, template: str) -> str:
    t = report.markdown_table
    def rows(items, value=False):
        out = []
        for i, e in enumerate(items, 1):
            out.append({"n": i, "name": e["name"] + (" (stale value)" if e["valuation_stale"] else ""),
                        "club": e["club"], "league": e["league"], "age": e["age"],
                        "value_m": _m(e["market_value_eur"]),
                        "vdate": e["valuation_date"] or "-", "sim": e["similarity"], "cos": e["cosine"],
                        "mins": e["minutes"], "self": e.get("self_match_rank", "-"),
                        "srank": e.get("similarity_rank"), "vscore": e.get("value_score"),
                        "front": "yes" if e.get("on_frontier") else "", "ok": "yes" if e["meets_constraints"] else "no"})
        return out
    base = [("n", "#"), ("name", "Player"), ("club", "Club 2015/16"), ("league", "League"), ("age", "Age"),
            ("mins", "Minutes"), ("value_m", "Value (EUR m)"), ("vdate", "Valued on"), ("sim", "Similarity"),
            ("cos", "Cosine"), ("self", "Split-half rank")]
    keys = list(s["target"]["percentiles"])
    pct_rows = []
    for m in keys:
        r = {"metric": m.replace("_", " "), "target": s["target"]["percentiles"][m]}
        for i, e in enumerate(s["shortlist"][:3], 1):
            r[f"s{i}"] = e["percentiles"][m]
        pct_rows.append(r)
    gap_rows = [{"name": e["name"], **{g: e["group_gaps"][g] for g in s["settings"]["group_weights"]}}
                for e in s["shortlist"]]
    st = s["stability"]
    tables = {
        "top_similar": t(rows(s["top_similar"]), base + [("srank", "Similarity rank"), ("front", "Frontier"),
                                                         ("ok", "Meets constraints")]),
        "shortlist": t(rows(s["shortlist"]), base + [("srank", "Similarity rank"), ("vscore", "Value score"),
                                                     ("front", "Frontier")]),
        "frontier": t(rows(s["frontier"]), base + [("srank", "Similarity rank"), ("ok", "Meets constraints")]),
        "weights": t([{"group": g["label"], "weight": g["weight"],
                       "metrics": ", ".join(f"{m['name'].replace('_', ' ')} ({s['settings']['metric_weights'][m['name']]:.3f})"
                                            for m in g["metrics"])} for g in s["_groups"]],
                     [("group", "Group"), ("weight", "Group weight"), ("metrics", "Metrics (weight in the distance)")]),
        "percentiles": t(pct_rows, [("metric", "Metric"), ("target", s["target"]["name"])]
                         + [(f"s{i}", e["name"]) for i, e in enumerate(s["shortlist"][:3], 1)]),
        "gaps": t(gap_rows, [("name", "Player")] + [(g["name"], g["label"]) for g in s["_groups"]]),
        "stability": t([{"k": f"top {x['k']}", "players": x["players"], "share": x["share"], "chance": x["chance"]}
                        for x in st["top_k"]],
                       [("k", "Own profile in"), ("players", "Players"), ("share", "Share", "pct"),
                        ("chance", "By chance", "pct")]),
    }
    ctx = {**s, "fp_short": s["config_sha256"][:12], "cap_m": s["settings"]["budget_cap_eur"] / 1e6,
           "target_value_m": _m(s["target"]["market_value_eur"]),
           "top1": st["top_k"][0], "top5": st["top_k"][-1],
           "frontier_count": len(s["frontier"]),
           "frontier_eligible": sum(e["meets_constraints"] for e in s["frontier"]),
           "shortlist_stale": sum(bool(e["valuation_stale"]) for e in s["shortlist"]),
           "shortlist_on_frontier": sum(bool(e["on_frontier"]) for e in s["shortlist"]),
           "shortlist_no_split": sum("self_match_rank" not in e for e in s["shortlist"]),
           "stab_not_rated": st["pool_players"] - st["players"],
           "top5_miss": 1 - st["top_k"][-1]["share"], "n_metrics": len(s["settings"]["metric_weights"]),
           "overlap": len({e["statsbomb_player_id"] for e in s["shortlist"]}
                          & {e["statsbomb_player_id"] for e in s["top_similar"]})}
    return report.render_template(template, ctx, tables)


def main() -> dict:
    from recruit import r4_figures
    data, scope, cfg, metrics_cfg = (config.load(n) for n in ("data", "scope", "similarity", "metrics"))
    fp = fingerprint()
    start = time.time()
    con = load.connect(ROOT / data["duckdb"]["path"], data["duckdb"]["memory_limit"], data["duckdb"]["threads"])
    players, season, halves = read_inputs(con, scope, cfg)
    check_halves(con)
    con.close()
    res = analyse(players, season, halves, cfg, metrics_cfg)
    save_table(res["table"], ROOT / data["processed_dir"] / "r4")
    s = build_summary(res, cfg, fp)
    s["run"] = {"seconds": round(time.time() - start, 1), "peak_rss_bytes": flatten.peak_rss_bytes()}
    SUMMARY.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    s["figures"] = r4_figures.draw(res, s, cfg, FIGURES)
    DOC.write_text(render({**s, "_groups": cfg["groups"]}, TEMPLATE.read_text(encoding="utf-8")), encoding="utf-8")
    return s


if __name__ == "__main__":
    out = main()
    print(f"config {out['config_sha256']}")
    print(f"pool {out['pool']['pool']}, priced {out['pool']['priced']}, eligible {out['pool']['eligible']}")
