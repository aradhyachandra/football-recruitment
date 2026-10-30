"""R2: build player-season profiles in DuckDB (sql/r2_*.sql), save the prepared tables to
data/processed/r2/ (gitignored), save the summaries to results/r2_profiles_summary.json and render
docs/R2_profiles.md from docs/templates/R2_profiles.md.

    python -m recruit.run_r2

Needs the DuckDB database built by R1 (python -m recruit.run_r1). results/ gets summaries only: pool
sizes, metric percentiles by role, the possession-method comparison and the departing player's profile.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from recruit import config, flatten, load, profiles, report

ROOT = config.ROOT
SUMMARY = ROOT / "results" / "r2_profiles_summary.json"
TEMPLATE = ROOT / "docs" / "templates" / "R2_profiles.md"
DOC = ROOT / "docs" / "R2_profiles.md"
EXPORT_TABLES = ["r2_stints", "r2_team_possession", "r2_player_match", "r2_players", "r2_player_season"]


def export(con, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for t in EXPORT_TABLES:
        con.execute(f"COPY {t} TO '{(out_dir / f'{t}.parquet').as_posix()}' (FORMAT parquet)")
        counts[t] = int(con.execute(f"SELECT count(*) FROM {t}").fetchone()[0])
    return counts


def _names(con, sql: str) -> dict:
    return dict(con.execute(sql).fetchall())


def build_summary(con, scope: dict, cfg: dict) -> dict:
    prof_cfg, met_cfg = cfg["profiles"], cfg["metrics"]
    leagues = {c["competition_id"]: c["name"] for c in scope["competitions"]}
    labels = {m["name"]: m["label"] for m in met_cfg["metrics"]} | {r["name"]: r["label"] for r in met_cfg["ratios"]}
    adjusted = {m["name"] for m in met_cfg["metrics"] if m.get("possession_adjusted")}
    order = [m["name"] for m in met_cfg["metrics"] if m.get("in_profile", True)] + [r["name"] for r in met_cfg["ratios"]]
    threshold = prof_cfg["minutes"]["threshold"]
    team_names = _names(con, "SELECT DISTINCT team_id, team_name FROM sb_lineup_players")
    position_names = _names(con, "SELECT DISTINCT position_id, position_name FROM sb_lineup_positions")

    checks = profiles.checks(con, cfg)
    ref = prof_cfg["possession_adjustment"]["reference_opponent_share"]
    poss = profiles.possession_check(con)
    poss["adjustment_factor_min"] = ref / checks["max_opponent_share"]
    poss["adjustment_factor_max"] = ref / checks["min_opponent_share"]

    dist = profiles.distributions(con, cfg)
    for d in dist:
        d["label"] = labels[d["metric"]]
    pools = profiles.pool_sizes(con, scope, cfg)

    p = profiles.departing_player(con, scope)
    role_dist = {d["metric"]: d for d in dist if d["role"] == p["role"]}
    profile_rows = {r["metric"]: r for r in profiles.departing_profile(con, scope, cfg)}
    departing = {
        "statsbomb_player_id": int(p["player_id"]), "name": scope["departing_player"]["statsbomb_name"],
        "minutes": p["minutes"], "matches": int(p["matches"]), "role": p["role"], "role_share": p["role_share"],
        "avg_team_share": p["avg_team_share"],
        "over_threshold": p["minutes"] >= threshold, "moved_mid_season": p["moved_mid_season"],
        "teams": [{"team": team_names.get(t["team_id"], str(t["team_id"])),
                   "league": leagues[t["competition_id"]], "minutes": t["minutes"], "matches": int(t["matches"])}
                  for t in p["teams"]],
        "minutes_by_role": [{"role": r["role"], "minutes": r["minutes"]} for r in p["roles"]],
        "minutes_by_position": [{"position": position_names.get(r["position_id"], str(r["position_id"])),
                                 "minutes": r["minutes"]} for r in p["positions"]],
        "profile": [{"metric": m, "label": labels[m], "kind": profile_rows[m]["kind"],
                     "possession_adjusted": m in adjusted,
                     **{k: profile_rows[m][k] for k in ("total_raw", "total_adjusted", "value", "value_padj",
                                                       "pct_rank", "pct_rank_padj", "pool_size")},
                     "role_median": (role_dist.get(m) or {}).get("value", {}).get("p50"),
                     "role_median_padj": ((role_dist.get(m) or {}).get("value_padj") or {}).get("p50")}
                    for m in order],
    }
    return {
        "season_id": scope["season"]["season_id"],
        "minutes_threshold": threshold,
        "sensitivity_thresholds": prof_cfg["minutes"]["sensitivity_thresholds"],
        "possession_method": prof_cfg["possession"]["method"],
        "adjustment_formula": prof_cfg["possession_adjustment"]["formula"],
        "checks": checks,
        "team_minutes": profiles.team_minutes_check(con, cfg) | {
            "tolerance_share": prof_cfg["team_minutes_check"]["tolerance_share"]},
        "possession_check": poss,
        "pool_sizes": pools,
        "pool_totals": [{"threshold": t, "players": sum(r["players"] for r in pools if r["threshold"] == t)}
                        for t in prof_cfg["minutes"]["sensitivity_thresholds"]],
        "distributions": dist,
        "departing_player": departing,
    }


def _pool_table(s: dict, threshold: int, leagues: list[str]) -> str:
    pools = [r for r in s["pool_sizes"] if r["threshold"] == threshold]
    roles = list(dict.fromkeys(r["role"] for r in sorted(pools, key=lambda r: r["role"])))
    rows = []
    for role in roles + ["All roles"]:
        row = {"role": role}
        for lg in leagues:
            row[lg] = sum(r["players"] for r in pools
                          if r["league"] == lg and (role == "All roles" or r["role"] == role))
        row["total"] = sum(row[lg] for lg in leagues)
        rows.append(row)
    return report.markdown_table(rows, [("role", "Role")] + [(lg, lg) for lg in leagues] + [("total", "Total")])


def _threshold_table(s: dict) -> str:
    roles = sorted({r["role"] for r in s["pool_sizes"]})
    rows = [{"role": role, **{str(t): sum(r["players"] for r in s["pool_sizes"]
                                         if r["threshold"] == t and r["role"] == role)
                              for t in s["sensitivity_thresholds"]}} for role in roles]
    rows.append({"role": "All roles", **{str(t["threshold"]): t["players"] for t in s["pool_totals"]}})
    return report.markdown_table(rows, [("role", "Role")] + [(str(t), f"{t:,} min") for t in s["sensitivity_thresholds"]])


def render(s: dict, template: str, scope: dict) -> str:
    leagues = [c["name"] for c in scope["competitions"]]
    d = s["departing_player"]
    prof_rows = []
    for r in d["profile"]:
        ratio = r["kind"] == "ratio"
        prof_rows.append({
            "label": r["label"] + (" (share)" if ratio else ""),
            "value": f"{r['value']:.1%}" if ratio and r["value"] is not None else r["value"],
            "role_median": f"{r['role_median']:.1%}" if ratio and r["role_median"] is not None else r["role_median"],
            "pct_rank": r["pct_rank"],
            "value_padj": r["value_padj"], "role_median_padj": r["role_median_padj"],
            "pct_rank_padj": r["pct_rank_padj"]})
    defensive = [r for r in d["profile"] if r["possession_adjusted"]]
    tm = s["team_minutes"]
    ctx = {**s, **report.publication_context(), "d": d | {"statsbomb_player_id": str(d["statsbomb_player_id"])},
           "tm": {"above_excess_share": tm["above_excess_minutes"] / tm["all_minutes"]
                  if tm["above_excess_minutes"] else 0.0},
           "dm": {"top_quarter_padj": sum(1 for r in defensive if r["pct_rank_padj"] >= 0.75),
                  "defensive_metrics": len(defensive),
                  "pool_size": d["profile"][0]["pool_size"]}}
    t = report.markdown_table
    tables = {
        "pools": _pool_table(s, s["minutes_threshold"], leagues),
        "thresholds": _threshold_table(s),
        "departing_teams": t(d["teams"], [("team", "Team"), ("league", "League"), ("matches", "Matches"),
                                          ("minutes", "Minutes")]),
        "departing_roles": t(d["minutes_by_role"], [("role", "Role"), ("minutes", "Minutes")]),
        "departing_positions": t(d["minutes_by_position"], [("position", "StatsBomb position"),
                                                            ("minutes", "Minutes")]),
        "profile": t(prof_rows, [("label", "Metric"), ("value", "Per 90 (raw)"),
                                 ("role_median", "Role median"), ("pct_rank", "Percentile rank", "pct"),
                                 ("value_padj", "Per 90 (possession-adj.)"),
                                 ("role_median_padj", "Role median (adj.)"),
                                 ("pct_rank_padj", "Percentile rank (adj.)", "pct")]),
    }
    return report.render_template(template, ctx, tables)


def main() -> dict:
    data, scope = config.load("data"), config.load("scope")
    cfg = profiles.load_configs()
    start = time.time()
    con = load.connect(ROOT / data["duckdb"]["path"], data["duckdb"]["memory_limit"], data["duckdb"]["threads"])
    profiles.build(con, scope, cfg, log=lambda s: print(s, flush=True))
    counts = export(con, ROOT / data["processed_dir"] / "r2")
    s = build_summary(con, scope, cfg)
    con.close()
    s["run"] = {"seconds": round(time.time() - start, 1), "peak_rss_bytes": flatten.peak_rss_bytes(),
                "table_rows": counts}
    SUMMARY.write_text(json.dumps(s, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    DOC.write_text(render(s, TEMPLATE.read_text(encoding="utf-8"), scope), encoding="utf-8")
    return s


if __name__ == "__main__":
    out = main()
    d = out["departing_player"]
    print(f"{d['name']}: {d['role']}, {d['minutes']:.0f} min; pools at {out['minutes_threshold']}: "
          f"{next(t['players'] for t in out['pool_totals'] if t['threshold'] == out['minutes_threshold'])}")
