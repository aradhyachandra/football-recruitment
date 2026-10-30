"""R3: join the R2 player profiles to Transfermarkt market values, save the joined table to
data/processed/r3/ (gitignored), save summaries to results/r3_join_summary.json and render
docs/R3_market_values.md from docs/templates/R3_market_values.md.

    python -m recruit.run_r3

Needs the DuckDB database built by R1 and R2. results/ gets summaries only: match rates, method counts,
valuation gaps, plausibility flags, the departing player's record, a fixed-seed sample of matched
pairs (names, clubs, method) and the unmatched players (name, team, role).
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

from recruit import config, flatten, load, market_values, report

ROOT = config.ROOT
SUMMARY = ROOT / "results" / "r3_join_summary.json"
TEMPLATE = ROOT / "docs" / "templates" / "R3_market_values.md"
DOC = ROOT / "docs" / "R3_market_values.md"
EXPORT_TABLES = ["r3_player_values", "r3_plausibility", "r3_matches"]
GAP_BUCKETS = [(0, 30, "0-30 days"), (31, 90, "31-90 days"), (91, 183, "91-183 days"),
               (184, 365, "184-365 days"), (366, None, "over 365 days")]


def export(con, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for t in EXPORT_TABLES:
        con.execute(f"COPY {t} TO '{(out_dir / f'{t}.parquet').as_posix()}' (FORMAT parquet)")
        counts[t] = int(con.execute(f"SELECT count(*) FROM {t}").fetchone()[0])
    return counts


def _rate(rows: list[dict]) -> dict:
    n = len(rows)
    matched = sum(r["transfermarkt_player_id"] is not None for r in rows)
    priced = sum(r["market_value_eur"] is not None for r in rows)
    return {"players": n, "matched": matched, "match_rate": matched / n if n else None,
            "priced": priced, "priced_rate": priced / n if n else None}


def _quantiles(values: list[int]) -> dict:
    if not values:
        return {}
    v = sorted(values)
    pick = lambda q: v[min(len(v) - 1, int(q * (len(v) - 1) + 0.5))]  # nearest rank
    return {"p10": pick(0.1), "p25": pick(0.25), "median": pick(0.5), "p75": pick(0.75), "p90": pick(0.9),
            "max": v[-1]}


def _gaps(rows: list[dict], max_gap: int) -> dict:
    matched = [r for r in rows if r["transfermarkt_player_id"] is not None]
    gaps = [r["valuation_gap_days"] for r in matched if r["valuation_gap_days"] is not None]
    buckets = [{"bucket": label, "players": sum(lo <= g and (hi is None or g <= hi) for g in gaps)}
               for lo, hi, label in GAP_BUCKETS]
    return {"matched": len(matched), "with_valuation": len(gaps),
            "no_valuation_before_date": len(matched) - len(gaps),
            "stale": sum(g > max_gap for g in gaps), "quantiles_days": _quantiles(gaps), "buckets": buckets}


def build_summary(con, scope: dict, cfg: dict, club_rows: list[dict], club_map: dict, overrides: dict) -> dict:
    leagues = {c["competition_id"]: c["name"] for c in scope["competitions"]}
    thresholds = cfg["summary"]["minutes_thresholds"]
    focus = cfg["summary"]["focus_role"]
    sb_team = dict(con.execute("SELECT DISTINCT team_id, team_name FROM sb_lineup_players").fetchall())
    tm_club = {c["statsbomb_team_id"]: c["transfermarkt_name"] for c in club_map["clubs"]}
    rows = market_values._rows(con, """SELECT v.*, list_transform(p.teams, t -> t.team_id) AS team_ids
                                      FROM r3_player_values v JOIN r2_players p USING (player_id)
                                      ORDER BY v.player_id""")
    teams = lambda r: " / ".join(sb_team[t] for t in r["team_ids"])

    rates = []
    for t in thresholds:
        pool = [r for r in rows if r["minutes"] >= t]
        rates.append({"threshold": t, "league": "All", "role": "All", **_rate(pool)})
        for cid, name in leagues.items():
            rates.append({"threshold": t, "league": name, "role": "All",
                          **_rate([r for r in pool if r["main_competition_id"] == cid])})
        for role in sorted({r["role"] for r in rows}):
            rates.append({"threshold": t, "league": "All", "role": role,
                          **_rate([r for r in pool if r["role"] == role])})

    methods = []
    for t in thresholds:
        pool = [r for r in rows if r["minutes"] >= t and r["method"]]
        for m in sorted({r["method"] for r in pool}):
            methods.append({"threshold": t, "method": m, "players": sum(r["method"] == m for r in pool)})
    statuses = [{"status": s, "players": sum(r["status"] == s for r in rows)}
                for s in sorted({r["status"] for r in rows})]

    plaus = market_values._rows(con, "SELECT * FROM r3_plausibility")
    by_id = {r["player_id"]: r for r in rows}
    flagged = [{"statsbomb_name": by_id[p["player_id"]]["statsbomb_name"],
                "transfermarkt_name": by_id[p["player_id"]]["transfermarkt_name"],
                "team": sb_team[p["statsbomb_team_id"]], "sb_matches": p["sb_matches"],
                "tm_league_apps": p["tm_league_apps"], "method": by_id[p["player_id"]]["method"]}
               for p in plaus if p["gap_flag"]]
    diffs = [abs(p["sb_matches"] - p["tm_league_apps"]) for p in plaus]

    ids = scope["departing_player_ids"]
    d = by_id[ids["statsbomb_player_id"]]
    if d["transfermarkt_player_id"] != ids["transfermarkt_player_id"]:
        raise ValueError(f"departing player matched to Transfermarkt {d['transfermarkt_player_id']}, "
                         f"expected {ids['transfermarkt_player_id']} (config/scope.yaml)")
    departing = {k: d[k] for k in ("statsbomb_name", "transfermarkt_player_id", "transfermarkt_name", "method",
                                   "score", "market_value_eur", "valuation_gap_days", "valuation_stale", "age",
                                   "age_years", "plausibility_flag", "role")}
    departing |= {"statsbomb_player_id": ids["statsbomb_player_id"], "valuation_date": str(d["valuation_date"]),
                  "date_of_birth": str(d["date_of_birth"].date() if hasattr(d["date_of_birth"], "date")
                                       else d["date_of_birth"]),
                  "matches_expected_id": True, "team": teams(d)}

    matched = [r for r in rows if r["transfermarkt_player_id"] is not None]
    rng = random.Random(cfg["summary"]["sample_seed"])
    sample = rng.sample(matched, min(cfg["summary"]["sample_size"], len(matched)))
    in_squad = {(p["player_id"], p["statsbomb_team_id"]) for p in plaus if p["tm_all_apps"] > 0}
    sample_rows = [{"statsbomb_name": r["statsbomb_name"], "statsbomb_team": teams(r),
                    "transfermarkt_name": r["transfermarkt_name"],
                    "transfermarkt_club": " / ".join(tm_club[t] for t in r["team_ids"]
                                                     if (r["player_id"], t) in in_squad) or "-",
                    "method": r["method"]}
                   for r in sorted(sample, key=lambda r: r["statsbomb_name"])]

    unmatched = [{"name": r["statsbomb_name"], "team": teams(r), "role": r["role"]}
                 for r in sorted(rows, key=lambda r: -r["minutes"]) if r["transfermarkt_player_id"] is None]
    focus_900 = [r for r in rows if r["role"] == focus and r["minutes"] >= cfg["summary"]["minutes_thresholds"][-1]]

    return {
        "season_id": scope["season"]["season_id"],
        "valuation_date": scope["valuation_date"],
        "settings": {"min_score": cfg["min_score"], "ambiguity_margin": cfg["ambiguity_margin"],
                     "max_gap_days": cfg["valuation"]["max_gap_days"],
                     "max_abs_gap_matches": cfg["plausibility"]["max_abs_gap_matches"],
                     "club_date_overlap_min": cfg["club_date_overlap_min"],
                     "sample_seed": cfg["summary"]["sample_seed"], "overrides": len(overrides["overrides"]),
                     "overrides_outside_squad": sum(bool(o.get("outside_squad")) for o in overrides["overrides"])},
        "club_map": {"teams": len(club_rows), "transfermarkt_clubs": len({r["transfermarkt_club_id"] for r in club_rows}),
                     "by_league": [{"league": name, "teams": sum(r["competition_id"] == cid for r in club_rows)}
                                   for cid, name in leagues.items()],
                     "min_date_overlap": min(r["dates_covered"] / r["sb_matches"] for r in club_rows),
                     "teams_full_date_overlap": sum(r["dates_covered"] == r["sb_matches"] for r in club_rows)},
        "match_rates": rates,
        "focus_pool": {"role": focus, "threshold": cfg["summary"]["minutes_thresholds"][-1], **_rate(focus_900),
                       "stale": sum(bool(r["valuation_stale"]) for r in focus_900),
                       "unmatched": [{"name": r["statsbomb_name"], "team": teams(r)} for r in focus_900
                                     if r["transfermarkt_player_id"] is None]},
        "methods": methods,
        "statuses": statuses,
        "valuation_gaps": {str(t): _gaps([r for r in rows if r["minutes"] >= t], cfg["valuation"]["max_gap_days"])
                           for t in thresholds},
        "plausibility": {"player_clubs": len(plaus), "equal": sum(x == 0 for x in diffs),
                         "within_1": sum(x <= 1 for x in diffs), "flagged": len(flagged), "flagged_rows": flagged},
        "departing_player": departing,
        "sample": sample_rows,
        "unmatched": unmatched,
    }


def render(s: dict, template: str) -> str:
    t = report.markdown_table
    thr = [str(x["threshold"]) for x in s["match_rates"] if x["league"] == "All" and x["role"] == "All"]
    def rate_table(key):
        names = list(dict.fromkeys(r[key] for r in s["match_rates"] if r[key] != "All"))
        out = []
        for name in names + ["All"]:
            row = {"name": name}
            for r in s["match_rates"]:
                if r[key] == name and (key == "league" and r["role"] == "All" or key == "role" and r["league"] == "All"):
                    row[f"n{r['threshold']}"], row[f"m{r['threshold']}"] = r["players"], r["matched"]
                    row[f"p{r['threshold']}"] = r["priced"]
            out.append(row)
        cols = [("name", key.capitalize())]
        for x in thr:
            cols += [(f"n{x}", f"Players ({x}+ min)"), (f"m{x}", f"Matched ({x}+)"), (f"p{x}", f"Priced ({x}+)")]
        return t(out, cols)
    method_rows = []
    for m in sorted({r["method"] for r in s["methods"]}):
        method_rows.append({"method": m, **{x: next((r["players"] for r in s["methods"]
                                                     if r["method"] == m and str(r["threshold"]) == x), 0) for x in thr}})
    gaps = s["valuation_gaps"]
    gap_rows = [{"bucket": b["bucket"], **{x: next(g["players"] for g in gaps[x]["buckets"] if g["bucket"] == b["bucket"])
                                           for x in thr}} for b in gaps[thr[0]]["buckets"]]
    gap_rows.append({"bucket": "no valuation on or before the date", **{x: gaps[x]["no_valuation_before_date"] for x in thr}})
    d = s["departing_player"]
    ctx = {**s, **report.publication_context(), "seed": str(s["settings"]["sample_seed"]), "d": d | {"transfermarkt_player_id": str(d["transfermarkt_player_id"]),
                          "statsbomb_player_id": str(d["statsbomb_player_id"]),
                          "value_m": d["market_value_eur"] / 1e6},
           "all": {x: next(r for r in s["match_rates"] if r["league"] == "All" and r["role"] == "All"
                           and str(r["threshold"]) == x) for x in thr},
           "unmatched_count": len(s["unmatched"]), "sample_count": len(s["sample"])}
    tables = {
        "leagues": rate_table("league"), "roles": rate_table("role"),
        "methods": t(method_rows, [("method", "Method")] + [(x, f"Players ({x}+ min)") for x in thr]),
        "statuses": t(s["statuses"], [("status", "Status"), ("players", "Players")]),
        "gaps": t(gap_rows, [("bucket", "Valuation age at the date")] + [(x, f"Matched players ({x}+ min)") for x in thr]),
        "flagged": t(s["plausibility"]["flagged_rows"], [("statsbomb_name", "StatsBomb name"), ("team", "Team"),
                                                         ("sb_matches", "StatsBomb matches"),
                                                         ("tm_league_apps", "Transfermarkt league apps"),
                                                         ("method", "Method")]),
        "sample": t(s["sample"], [("statsbomb_name", "StatsBomb name"), ("statsbomb_team", "StatsBomb team"),
                                  ("transfermarkt_name", "Transfermarkt name"),
                                  ("transfermarkt_club", "Transfermarkt club"), ("method", "Method")]),
        "unmatched": t(s["unmatched"], [("name", "Name"), ("team", "Team"), ("role", "Role")]),
    }
    return report.render_template(template, ctx, tables)


def main() -> dict:
    data, scope = config.load("data"), config.load("scope")
    cfg, club_map, overrides = config.load("matching"), config.load("club_map"), config.load("player_overrides")
    start = time.time()
    con = load.connect(ROOT / data["duckdb"]["path"], data["duckdb"]["memory_limit"], data["duckdb"]["threads"])
    club_rows = market_values.build(con, scope, club_map, overrides, cfg, log=lambda s: print(s, flush=True))
    counts = export(con, ROOT / data["processed_dir"] / "r3")
    s = build_summary(con, scope, cfg, club_rows, club_map, overrides)
    con.close()
    s["run"] = {"seconds": round(time.time() - start, 1), "peak_rss_bytes": flatten.peak_rss_bytes(),
                "table_rows": counts}
    SUMMARY.write_text(json.dumps(s, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    DOC.write_text(render(s, TEMPLATE.read_text(encoding="utf-8")), encoding="utf-8")
    return s


if __name__ == "__main__":
    out = main()
    a = next(r for r in out["match_rates"] if r["league"] == "All" and r["role"] == "All" and r["threshold"] == 0)
    d = out["departing_player"]
    print(f"matched {a['matched']}/{a['players']}; {d['statsbomb_name']} -> {d['transfermarkt_player_id']}, "
          f"EUR {d['market_value_eur']:,} on {d['valuation_date']}")
