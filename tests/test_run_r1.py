"""End to end on the fixtures: build the R1 report and render the doc template from it."""
import json

from recruit import config, flatten, load, raw_files, run_r1
from tests.test_audit import SCOPE


def test_report_and_doc_render_from_fixtures(sb_raw, tm_raw, fields, tmp_path):
    stats = flatten.flatten_all(sb_raw, tmp_path / "p", 27, [2, 7], fields)
    con = load.connect(":memory:", "1GB", 1)
    load.load_statsbomb(con, tmp_path / "p", fields)
    load.load_transfermarkt(con, {t: tm_raw / f"{t}.csv" for t in load.TM_TABLES})
    fp = {"statsbomb": raw_files.fingerprint_statsbomb(sb_raw, 27, [2, 7]),
          "transfermarkt": raw_files.fingerprint_transfermarkt(tm_raw, load.TM_TABLES, suffix=".csv")}
    sizes = run_r1.source_sizes(fp) | {"parquet_bytes": run_r1.dir_bytes(tmp_path / "p", "*.parquet"),
                                       "duckdb_bytes": 0}
    rep = run_r1.build_report(con, SCOPE | {"season": {"season_id": 27}}, config.load("audit"),
                              stats, sizes, fp)
    json.dumps(rep)  # the saved report must be plain JSON
    assert rep["gates"]["resource"]["statsbomb_raw_files"] == 7
    assert rep["gates"]["valuation"]["passed"] is False  # 1 of 3 fixture players is below 80%
    assert rep["all_gates_passed"] is False
    doc = run_r1.render(rep, run_r1.TEMPLATE.read_text(encoding="utf-8"))
    assert "{{" not in doc
    assert "| Premier League | 1 | 2 | 9 | 5 | 4 |" in doc
    assert "**FAIL**" in doc and "33.3%" in doc


def test_audit_only_reads_existing_db_and_keeps_full_run_sizes(sb_raw, tm_raw, fields, tmp_path):
    stats = flatten.flatten_all(sb_raw, tmp_path / "p", 27, [2, 7], fields)
    db = tmp_path / "r.duckdb"
    con = load.connect(db, "1GB", 1)
    load.load_statsbomb(con, tmp_path / "p", fields)
    load.load_transfermarkt(con, {t: tm_raw / f"{t}.csv" for t in load.TM_TABLES})
    con.close()
    fp = {"statsbomb": raw_files.fingerprint_statsbomb(sb_raw, 27, [2, 7]),
          "transfermarkt": raw_files.fingerprint_transfermarkt(tm_raw, load.TM_TABLES, suffix=".csv")}
    previous = {"gates": {"resource": {"parquet_bytes": 111, "duckdb_bytes": 222, "run_peak_rss_bytes": 333}}}
    rep = run_r1.audit_only(db, SCOPE | {"season": {"season_id": 27}}, config.load("audit"), stats, fp, previous)
    res = rep["gates"]["resource"]
    assert (res["parquet_bytes"], res["duckdb_bytes"], res["run_peak_rss_bytes"]) == (111, 222, 333)
    assert [h["date"] for h in rep["gates"]["valuation"]["departing_player"]["history"]] == ["2015-07-01", "2016-02-01"]
    doc = run_r1.render(rep, run_r1.TEMPLATE.read_text(encoding="utf-8"))
    assert "{{" not in doc and "2016-07-15" not in doc and "Chelsea" not in doc
