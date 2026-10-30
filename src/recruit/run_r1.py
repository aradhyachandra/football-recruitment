"""R1: verify raw-file fingerprints, flatten StatsBomb JSON to parquet, load everything into DuckDB,
run the data audit and its four gates, save results/r1_data_report.json and render
docs/R1_data_audit.md from docs/templates/R1_data_audit.md.

    python -m recruit.run_r1 --record        # first run only: record the raw-file fingerprints
    python -m recruit.run_r1                 # verify, flatten, load, audit
    python -m recruit.run_r1 --skip-flatten  # reuse data/processed/ parquet from an earlier run
    python -m recruit.run_r1 --audit-only    # verify, re-run the audit on the existing DuckDB, render

--audit-only leaves the database alone (later milestones keep their tables in it) and carries the
size and memory figures over from the last full run, since they describe that run.

Exits with status 1 if any gate fails (the report is still written so the numbers can be read).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import duckdb

from recruit import audit, config, flatten, load, raw_files, report

ROOT = config.ROOT
FINGERPRINTS = config.CONFIG_DIR / "raw_files.yaml"
REPORT = ROOT / "results" / "r1_data_report.json"
TEMPLATE = ROOT / "docs" / "templates" / "R1_data_audit.md"
DOC = ROOT / "docs" / "R1_data_audit.md"
GATES = ["valuation", "pressure", "lineup", "resource"]


def dir_bytes(path: Path, pattern: str) -> int:
    return sum(p.stat().st_size for p in Path(path).rglob(pattern) if p.is_file())


def source_sizes(fp: dict) -> dict:
    sb, tm = fp["statsbomb"].values(), fp["transfermarkt"].values()
    return {"statsbomb_raw_bytes": sum(g["bytes"] for g in sb),
            "statsbomb_raw_files": sum(g["files"] for g in sb),
            "transfermarkt_raw_bytes": sum(t["bytes"] for t in tm),
            "transfermarkt_raw_files": len(fp["transfermarkt"])}


def build_report(con, scope: dict, cfg: dict, flatten_stats: dict, sizes: dict, fp: dict) -> dict:
    gates = {"valuation": audit.valuation_gate(con, scope, cfg),
             "pressure": audit.pressure_gate(con, scope, cfg),
             "lineup": audit.lineup_gate(con, scope, cfg),
             "resource": audit.resource_gate(flatten_stats, sizes, cfg)}
    return {
        "season_id": scope["season"]["season_id"],
        "valuation_date": scope["valuation_date"],
        "leagues": audit.league_summary(con, scope),
        "event_types": audit.event_type_counts(con, scope),
        "row_counts": load.row_counts(con),
        "departing_player_statsbomb": audit.departing_player_statsbomb(con, scope),
        "raw_files": {"statsbomb": {k: {"files": g["files"], "bytes": g["bytes"],
                                        "records": g.get("records")} for k, g in fp["statsbomb"].items()},
                      "transfermarkt": {k: {"bytes": t["bytes"], "data_rows": t.get("data_rows")}
                                        for k, t in fp["transfermarkt"].items()}},
        "gates": gates,
        "all_gates_passed": all(gates[g]["passed"] for g in GATES),
    }


def _mb(n: int) -> float:
    return n / 2**20


def render(rep: dict, template: str) -> str:
    leagues = [l["league"] for l in rep["leagues"]]
    g = rep["gates"]
    res = g["resource"]
    ctx = {**rep, **report.publication_context(), "status": {k: "PASS" if g[k]["passed"] else "FAIL" for k in GATES},
           "sizes": {"statsbomb_raw_mb": _mb(res["statsbomb_raw_bytes"]),
                     "transfermarkt_raw_mb": _mb(res["transfermarkt_raw_bytes"]),
                     "parquet_mb": _mb(res["parquet_bytes"]), "duckdb_mb": _mb(res["duckdb_bytes"]),
                     "peak_rss_mb": _mb(res["flatten_peak_rss_bytes"]),
                     "run_peak_rss_mb": _mb(res.get("run_peak_rss_bytes", 0)),
                     "max_peak_rss_mb": res["max_peak_rss_gb"] * 1024}}
    t = report.markdown_table
    tables = {
        "leagues": t(rep["leagues"], [("league", "League"), ("matches", "Matches"), ("teams", "Teams"),
                                      ("events", "Events"), ("squad_players", "Players in squads"),
                                      ("players_who_played", "Players who played")]),
        "event_types": t(rep["event_types"], [("type_name", "Event type")] + [(l, l) for l in leagues]
                         + [("total", "Total")]),
        "valuation_by_league": t(g["valuation"]["by_league"] + [{"league": "All four", **{
            k: g["valuation"][k] for k in ("players", "with_valuation_before", "share_before")}}],
            [("league", "League (Transfermarkt code)"), ("players", "Players"),
             ("with_valuation_before", "Valued in 6 months before"), ("share_before", "Share", "pct")]),
        "departing_history": t(g["valuation"]["departing_player"]["history"],
                               [("date", "Date"), ("market_value_eur", "Market value (EUR)"),
                                ("club", "Club on the record"), ("days_before", "Days before 2016-07-01")]),
        "departing_statsbomb": t(rep["departing_player_statsbomb"],
                                 [("player_id", "StatsBomb id"), ("player_name", "Name"), ("team_name", "Team"),
                                  ("matches_listed", "Matches in squad"), ("matches_played", "Matches played")]),
        "pressure": t(g["pressure"]["by_league"], [("league", "League"), ("pressure_events", "Pressure events"),
                                                   ("matches", "Matches"),
                                                   ("matches_with_pressure", "Matches with pressures")]),
        "open_ended": t(g["lineup"]["open_ended_by_end_reason"], [("end_reason", "End reason"),
                                                                 ("rows", "Stints")]),
        "row_counts": t([{"table": k, "rows": v} for k, v in rep["row_counts"].items()],
                        [("table", "DuckDB table"), ("rows", "Rows")]),
    }
    return report.render_template(template, ctx, tables)


RESOURCE_FROM_FULL_RUN = ("parquet_bytes", "duckdb_bytes")


def write_outputs(rep: dict) -> None:
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    DOC.write_text(render(rep, TEMPLATE.read_text(encoding="utf-8")), encoding="utf-8")
    for gname in GATES:
        print(f"gate {gname}: {'PASS' if rep['gates'][gname]['passed'] else 'FAIL'}", flush=True)


def audit_only(db: Path, scope: dict, cfg: dict, flatten_stats: dict, fp: dict, previous: dict) -> dict:
    """Re-run the audit queries on the existing database; sizes and memory come from the last full run."""
    res = previous["gates"]["resource"]
    sizes = source_sizes(fp) | {k: res[k] for k in RESOURCE_FROM_FULL_RUN}
    con = duckdb.connect(str(db), read_only=True)
    rep = build_report(con, scope, cfg, flatten_stats, sizes, fp)
    con.close()
    rep["gates"]["resource"]["run_peak_rss_bytes"] = res["run_peak_rss_bytes"]
    return rep


def main(record: bool = False, skip_flatten: bool = False, audit_only_run: bool = False) -> dict:
    data, scope, cfg = config.load("data"), config.load("scope"), config.load("audit")
    season, cids = scope["season"]["season_id"], config.competition_ids(scope)
    sb_dir, tm_dir = ROOT / data["statsbomb"]["raw_dir"], ROOT / data["transfermarkt"]["raw_dir"]
    tables = data["transfermarkt"]["tables"]
    processed = ROOT / data["processed_dir"]

    if record:
        raw_files.write_fingerprints(
            {"statsbomb": raw_files.fingerprint_statsbomb(sb_dir, season, cids),
             "transfermarkt": raw_files.fingerprint_transfermarkt(tm_dir, tables)}, FINGERPRINTS)
    fp = raw_files.read_fingerprints(FINGERPRINTS)
    raw_files.verify(sb_dir, tm_dir, season, cids, tables, fp)
    print("raw files match config/raw_files.yaml", flush=True)

    db = ROOT / data["duckdb"]["path"]
    if audit_only_run:
        flatten_stats = json.loads((processed / flatten.STATS_FILE).read_text(encoding="utf-8"))
        rep = audit_only(db, scope, cfg, flatten_stats, fp, json.loads(REPORT.read_text(encoding="utf-8")))
        write_outputs(rep)
        return rep

    if not skip_flatten:  # own process, so its peak memory is the flatten step's alone
        subprocess.run([sys.executable, "-m", "recruit.flatten"], check=True, cwd=ROOT)
    flatten_stats = json.loads((processed / flatten.STATS_FILE).read_text(encoding="utf-8"))

    for f in (db, db.with_name(db.name + ".wal")):
        f.unlink(missing_ok=True)  # rebuilt from parquet and raw CSVs on every run
    con = load.connect(db, data["duckdb"]["memory_limit"], data["duckdb"]["threads"])
    load.load_statsbomb(con, processed, config.load("statsbomb_fields"))
    load.load_transfermarkt(con, {t: tm_dir / f"{t}.csv.gz" for t in tables})
    con.execute("CHECKPOINT")
    sizes = source_sizes(fp) | {"parquet_bytes": dir_bytes(processed, "*.parquet"),
                                "duckdb_bytes": db.stat().st_size}
    rep = build_report(con, scope, cfg, flatten_stats, sizes, fp)
    con.close()
    rep["gates"]["resource"]["run_peak_rss_bytes"] = flatten.peak_rss_bytes()

    write_outputs(rep)
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="record raw-file fingerprints (first run)")
    ap.add_argument("--skip-flatten", action="store_true", help="reuse the existing parquet files")
    ap.add_argument("--audit-only", action="store_true", help="audit the existing DuckDB and render only")
    a = ap.parse_args()
    sys.exit(0 if main(a.record, a.skip_flatten, a.audit_only)["all_gates_passed"] else 1)
