"""R5 docs: the derived figures the report needs (saved into results/r5_sensitivity.json so every number
in the report is in results/), docs/R5_sensitivity.md and the findings report docs/REPORT.md, both
rendered from docs/templates/ with results/ r1-r5 only."""
from __future__ import annotations

import json

from recruit import config, report

ROOT = config.ROOT
RESULTS = ROOT / "results"
TEMPLATES = ROOT / "docs" / "templates"
DOCS = ROOT / "docs"
ROLE_NAMES = ["Recommendation", "Backup 1", "Backup 2"]


def load_results() -> dict:
    names = {"r1": "r1_data_report", "r2": "r2_profiles_summary", "r3": "r3_join_summary", "r4": "r4_shortlist"}
    return {k: json.loads((RESULTS / f"{v}.json").read_text(encoding="utf-8")) for k, v in names.items()}


def _m(eur):
    """EUR to EUR m, whole numbers without decimals (10, not 10.00)."""
    if eur is None:
        return None
    m = eur / 1e6
    return int(m) if float(m).is_integer() else m


def _pct100(x):
    return None if x is None else round(100 * x)


def tradeoffs(c: dict, target: dict, labels: dict, count: int) -> list[dict]:
    """The key metrics where the player's percentile differs most from the target's (largest first)."""
    diffs = [(m, c["percentiles"][m], target["percentiles"][m]) for m in target["percentiles"]]
    diffs.sort(key=lambda x: -abs(x[1] - x[2]))
    return [{"metric": m, "label": labels.get(m, m.replace("_", " ")), "player_pct": _pct100(p),
             "target_pct": _pct100(t), "direction": "above" if p > t else "below"} for m, p, t in diffs[:count]]


def facts(s: dict, r: dict) -> dict:
    """Figures derived for the report from r1-r5 (kept small; saved with the R5 results)."""
    labels = {p["metric"]: p["label"] for p in r["r2"]["departing_player"]["profile"]}
    by_id = {c["statsbomb_player_id"]: c for c in s["candidates"]}
    n = s["settings"]["tradeoff_metrics"]
    picks = []
    for role, p in zip(ROLE_NAMES, s["recommendation"]):
        c = by_id[p["player_id"]]
        gaps = c["group_gaps"]
        picks.append({"role": role, "statsbomb_player_id": p["player_id"], "name": c["name"], "in_core": p["in_core"],
                      "tradeoffs": tradeoffs(c, s["target"], labels, n),
                      "largest_gap_group": max(gaps, key=gaps.get), "smallest_gap_group": min(gaps, key=gaps.get)})
    r4 = r["r4"]
    short_ids = {e["statsbomb_player_id"] for e in r4["shortlist"]}
    top_ids = {e["statsbomb_player_id"] for e in r4["top_similar"]}
    core = [by_id[i]["name"] for i in s["robust_core"]]
    closest = [e for e in r4["top_similar"] if e["meets_constraints"]]
    max_minutes = max(x["changes"].get("pool.min_minutes", r4["pool"]["min_minutes"]) for x in s["scenarios"])
    for p in picks:
        p["minutes_above_max_threshold"] = by_id[p["statsbomb_player_id"]]["minutes"] - max_minutes
    return {"core_size": len(core), "core_names": core, "picks": picks,
            "r4_shortlist_in_top_similar": len(short_ids & top_ids),
            "r4_shortlist_no_split_half": sum("self_match_rank" not in e for e in r4["shortlist"]),
            "cap_m": _m(r4["settings"]["budget_cap_eur"]),
            "target_value_m": _m(r4["target"]["market_value_eur"]),
            "core_line_scenarios": round(s["settings"]["robust_core_min_share"] * s["named"]["scenarios"]),
            "picks_outside_core": sum(not p["in_core"] for p in picks),
            "q_lo": round(100 * s["settings"]["draw_rank_quantiles"][0]),
            "q_hi": round(100 * s["settings"]["draw_rank_quantiles"][1]),
            "n_metrics": len(r4["settings"]["metric_weights"]), "max_minutes_threshold": max_minutes,
            "closest_eligible": [{"statsbomb_player_id": e["statsbomb_player_id"], "name": e["name"],
                                  "in_core": e["statsbomb_player_id"] in s["robust_core"]} for e in closest]}


# ---------- tables ----------

def _range(a: dict, lo="min_rank", hi="max_rank") -> str:
    if a.get(lo) is None:
        return "-"
    return f"{a[lo]:.0f}-{a[hi]:.0f}" if a[lo] != a[hi] else f"{a[lo]:.0f}"


def tables(s: dict, r: dict, f: dict) -> dict:
    N, K = s["settings"]["top_n"], s["settings"]["top_k"]
    t = report.markdown_table
    prof = [{"label": p["label"], "raw": p["value"], "adj": p["value_padj"], "pct": _pct100(p["pct_rank"]),
             "pct_adj": _pct100(p["pct_rank_padj"]), "median": p["role_median"]}
            for p in r["r2"]["departing_player"]["profile"]]

    def player_rows(items):
        return [{"n": i, "name": e["name"] + (" (stale value)" if e["valuation_stale"] else ""), "club": e["club"],
                 "league": e["league"], "age": e["age"], "mins": e["minutes"],
                 "value_m": e["market_value_eur"] / 1e6, "sim": e["similarity"], "srank": e.get("similarity_rank"),
                 "vrank": e.get("value_rank"), "self": e.get("self_match_rank", "not rated")}
                for i, e in enumerate(items, 1)]
    pcols = [("n", "#"), ("name", "Player"), ("club", f"Club {config.season_label()}"), ("age", "Age"), ("mins", "Minutes"),
             ("value_m", "Value (EUR m)"), ("sim", "Similarity"), ("srank", "Similarity rank")]
    by_id = {c["statsbomb_player_id"]: c for c in s["candidates"]}
    from recruit.r5_figures import main_candidates
    main = main_candidates(s, s["settings"]["figure_min_share"])
    robust = [{"name": c["name"] + (" (stale value)" if c["valuation_stale"] else ""),
               "core": "yes" if c["in_core"] else "", "value_m": c["market_value_eur"] / 1e6, "age": c["age"],
               "n_top": c["value_named"]["share_top_n"], "n_topk": c["value_named"]["share_top_k"],
               "n_med": c["value_named"].get("median_rank"), "n_range": _range(c["value_named"]),
               "d_top": c["value_draws"]["share_top_n"], "d_topk": c["value_draws"]["share_top_k"],
               "d_range": _range(c["value_draws"], "p05_rank", "p95_rank"),
               "s_top": c["similarity_named"]["share_top_n"], "sd_top": c["similarity_draws"]["share_top_n"]}
              for c in main]
    sim_rows = sorted(s["candidates"], key=lambda c: (-c["similarity_named"]["share_top_n"],
                                                      -(c["similarity_named"].get("median_similarity") or 0)))
    sim_rows = [{"name": c["name"], "value_m": c["market_value_eur"] / 1e6 if c["market_value_eur"] else None,
                 "age": c["age"], "s_top": c["similarity_named"]["share_top_n"],
                 "s_med": c["similarity_named"].get("median_rank"), "s_range": _range(c["similarity_named"]),
                 "sd_top": c["similarity_draws"]["share_top_n"], "n_top": c["value_named"]["share_top_n"]}
                for c in sim_rows if c["similarity_named"]["share_top_n"] >= s["settings"]["figure_min_share"]]
    scen = [{"label": x["label"], "pool": x["pool"], "eligible": x["eligible"], "overlap": x["overlap_with_base"],
             "top3": ", ".join(by_id[i]["name"] if i in by_id else str(i) for i in x["value_top_n"][:s["settings"]["top_k"]])}
            for x in s["scenarios"]]
    picks = []
    for p in f["picks"]:
        c = by_id[p["statsbomb_player_id"]]
        picks.append({"role": p["role"], "name": c["name"], "club": c["club"], "league": c["league"], "age": c["age"],
                      "mins": c["minutes"], "value_m": c["market_value_eur"] / 1e6, "vdate": c["valuation_date"],
                      "sim": c["similarity"], "srank": c["similarity_rank"], "vrank": c.get("value_rank"),
                      "n_top": c["value_named"]["share_top_n"], "n_topk": c["value_named"]["share_top_k"],
                      "d_top": c["value_draws"]["share_top_n"], "self": c.get("self_match_rank", "not rated"),
                      "cos": c["cosine"]})
    labels = {p["metric"]: p["label"] for p in r["r2"]["departing_player"]["profile"]}
    pct = [{"metric": labels.get(m, m), "target": _pct100(s["target"]["percentiles"][m]),
            **{f"p{i}": _pct100(by_id[p["statsbomb_player_id"]]["percentiles"][m]) for i, p in enumerate(f["picks"])}}
           for m in s["target"]["percentiles"]]
    gl = {g: g.replace("_", " ").capitalize() for g in r["r4"]["settings"]["group_weights"]}
    gaps = [{"name": by_id[p["statsbomb_player_id"]]["name"],
             **{g: by_id[p["statsbomb_player_id"]]["group_gaps"][g] for g in gl}} for p in f["picks"]]
    leagues = [{"league": x["league"], "matches": x["matches"], "teams": x["teams"], "played": x["players_who_played"]}
               for x in r["r1"]["leagues"]]
    weights = [{"group": gl[g], "w": w} for g, w in r["r4"]["settings"]["group_weights"].items()]
    return {
        "leagues": t(leagues, [("league", "League"), ("teams", "Teams"), ("matches", "Matches"),
                               ("played", "Players who played")]),
        "kante_profile": t(prof, [("label", "Metric (per 90 unless stated)"), ("raw", "Raw"),
                                  ("adj", "Possession-adjusted"), ("pct", "Percentile, raw"),
                                  ("pct_adj", "Percentile, adjusted"), ("median", "Pool median, raw")]),
        "weights": t(weights, [("group", "Metric group"), ("w", "Weight")]),
        "top_similar": t(player_rows(r["r4"]["top_similar"]), pcols + [("vrank", "Value rank")]),
        "shortlist": t(player_rows(r["r4"]["shortlist"]), pcols + [("vrank", "Value rank"), ("self", "Split-half rank")]),
        "scenarios": t(scen, [("label", "Scenario (one change from the base)"), ("pool", "Pool"),
                              ("eligible", "Eligible"), ("overlap", f"Top-{N} overlap with base"),
                              ("top3", f"Top {K} by value")]),
        "robust": t(robust, [("name", "Player"), ("core", "Robust core"), ("value_m", "Value (EUR m)"), ("age", "Age"),
                             ("n_top", f"Top {N}, scenarios", "pct"), ("n_topk", f"Top {K}, scenarios", "pct"),
                             ("n_med", "Median rank"), ("n_range", "Rank range"),
                             ("d_top", f"Top {N}, random weights", "pct"), ("d_topk", f"Top {K}, random weights", "pct"),
                             ("d_range", f"Rank {report.fmt(f['q_lo'], 'ord')}-{report.fmt(f['q_hi'], 'ord')} pct, random"),
                             ("s_top", f"Similarity top {N}, scenarios", "pct")]),
        "similarity_view": t(sim_rows, [("name", "Player"), ("value_m", "Value (EUR m)"), ("age", "Age"),
                                        ("s_top", f"Similarity top {N}, scenarios", "pct"), ("s_med", "Median similarity rank"),
                                        ("s_range", "Range"), ("sd_top", f"Similarity top {N}, random weights", "pct"),
                                        ("n_top", f"Value top {N}, scenarios", "pct")]),
        "picks": t(picks, [("role", ""), ("name", "Player"), ("club", f"Club {config.season_label()}"), ("league", "League"),
                           ("age", "Age"), ("mins", "Minutes"), ("value_m", "Value (EUR m)"), ("vdate", "Valued on"),
                           ("sim", "Similarity"), ("srank", "Similarity rank"), ("n_top", f"Top {N}, scenarios", "pct"),
                           ("n_topk", f"Top {K}, scenarios", "pct"), ("d_top", f"Top {N}, random weights", "pct"),
                           ("self", "Split-half rank")]),
        "picks_pct": t(pct, [("metric", "Key metric (percentile in the pool)"), ("target", s["target"]["name"])]
                       + [(f"p{i}", p["name"]) for i, p in enumerate(f["picks"])]),
        "picks_gaps": t(gaps, [("name", "Player")] + [(g, l) for g, l in gl.items()]),
        "closest_eligible": t([{"name": c["name"], "club": c["club"], "age": c["age"],
                                "value_m": c["market_value_eur"] / 1e6, "sim": c["similarity"],
                                "srank": c["similarity_rank"], "core": "yes" if c["in_core"] else "no",
                                "n_top": c["value_named"]["share_top_n"], "n_topk": c["value_named"]["share_top_k"],
                                "s_top": c["similarity_named"]["share_top_n"]}
                               for c in (by_id[e["statsbomb_player_id"]] for e in f["closest_eligible"])],
                              [("name", "Player"), ("club", f"Club {config.season_label()}"), ("age", "Age"),
                               ("value_m", "Value (EUR m)"), ("sim", "Similarity"), ("srank", "Similarity rank"),
                               ("core", "Robust core"), ("n_top", f"Value top {N}, scenarios", "pct"),
                               ("n_topk", f"Value top {K}, scenarios", "pct"),
                               ("s_top", f"Similarity top {N}, scenarios", "pct")]),
        "stability": t([{"k": f"top {x['k']}", "players": x["players"], "share": x["share"], "chance": x["chance"]}
                        for x in r["r4"]["stability"]["top_k"]],
                       [("k", "Own second-half profile in the"), ("players", "Players"), ("share", "Share", "pct"),
                        ("chance", "Expected by chance", "pct")]),
    }


def tradeoff_text(p: dict, target_name: str) -> str:
    parts = [f"{x['direction']} on {x['label'].lower()} ({x['player_pct']} vs {x['target_pct']})"
             for x in p["tradeoffs"]]
    return "; ".join(parts)


def context(s: dict, r: dict, f: dict) -> dict:
    by_id = {c["statsbomb_player_id"]: c for c in s["candidates"]}
    picks = []
    for p in f["picks"]:
        c = by_id[p["statsbomb_player_id"]]
        picks.append({**c, **p, "value_m": _m(c["market_value_eur"]),
                      "tradeoff_text": tradeoff_text(p, s["target"]["name"]),
                      "largest_gap": p["largest_gap_group"].replace("_", " "),
                      "smallest_gap": p["smallest_gap_group"].replace("_", " "),
                      "self_text": (f"his first-half profile found his own second half at rank {c['self_match_rank']}"
                                    if "self_match_rank" in c else
                                    "he had too few minutes in one half of the season for the split-half check")})
    kp = {p["metric"]: p for p in r["r2"]["departing_player"]["profile"]}
    pct = {m: {"raw": _pct100(p["pct_rank"]), "adj": _pct100(p["pct_rank_padj"])} for m, p in kp.items()}
    st = r["r4"]["stability"]
    return {**s, **r, **report.publication_context(), "f": f, "picks": picks, "kpct": pct, "fp_short": s["config_files"]["config/sensitivity.yaml"][:12],
            "sim_fp_short": s["config_files"]["config/similarity.yaml"][:12],
            "fp_sens": s["config_files"]["config/sensitivity.yaml"], "fp_sim": s["config_files"]["config/similarity.yaml"],
            "top1": st["top_k"][0], "top5": st["top_k"][-1], "core_list": ", ".join(f["core_names"]),
            "team_share": r["r2"]["departing_player"]["avg_team_share"],
            "overall": r["r3"]["match_rates"][0], "unmatched": len(r["r3"]["unmatched"]),
            "stab_not_rated": st["pool_players"] - st["players"]}


def write_docs(s: dict, sens_cfg: dict | None = None) -> dict:
    """Adds the derived figures to s (the caller saves them), then renders both docs. Returns s."""
    r = load_results()
    f = facts(s, r)
    s["report_facts"] = f
    ctx, tabs = context(s, r, f), tables(s, r, f)
    for name in ("R5_sensitivity", "REPORT"):
        text = (TEMPLATES / f"{name}.md").read_text(encoding="utf-8")
        (DOCS / f"{name}.md").write_text(report.render_template(text, ctx, tabs), encoding="utf-8")
    return s
