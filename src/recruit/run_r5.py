"""R5: sensitivity of the shortlist, robust core, recommendation, figures and the findings report.

    python -m recruit.run_r5

Needs the DuckDB database built by R1-R3 and results/r4_shortlist.json. Settings: config/similarity.yaml
(the R4 base, its sha256 must equal the one saved in R4) and config/sensitivity.yaml (its sha256 is
saved with the results). results/r5_sensitivity.json holds summaries only; figures go to docs/figures/;
docs/R5_sensitivity.md and docs/REPORT.md are rendered from their templates using results/ r1-r5.
"""
from __future__ import annotations

import json
import time

from recruit import config, flatten, load, report_r5, run_r4
from recruit import sensitivity as sens

ROOT = config.ROOT
SENS_FILE = config.CONFIG_DIR / "sensitivity.yaml"
RESULTS = ROOT / "results"
SUMMARY = RESULTS / "r5_sensitivity.json"
FIGURES = ROOT / "docs" / "figures"


def check_base(s: dict, r4: dict, sim_fp: str) -> None:
    """The base must be the R4 analysis: same config file and the same shortlist."""
    if sim_fp != r4["config_sha256"]:
        raise ValueError("config/similarity.yaml changed since R4; the base case would not be R4")
    r4_ids = [e["statsbomb_player_id"] for e in r4["shortlist"]]
    if s["scenarios"][0]["value_top_n"] != r4_ids:
        raise ValueError(f"base scenario shortlist {s['scenarios'][0]['value_top_n']} differs from R4 {r4_ids}")


def main() -> dict:
    from recruit import r5_figures
    data, scope, base_cfg, sens_cfg, metrics_cfg = (config.load(n) for n in
                                                     ("data", "scope", "similarity", "sensitivity", "metrics"))
    r4 = json.loads((RESULTS / "r4_shortlist.json").read_text(encoding="utf-8"))
    sim_fp, sens_fp = run_r4.fingerprint(), run_r4.fingerprint(SENS_FILE)
    start = time.time()
    con = load.connect(ROOT / data["duckdb"]["path"], data["duckdb"]["memory_limit"], data["duckdb"]["threads"])
    players, season, halves = run_r4.read_inputs(con, scope, base_cfg)
    con.close()
    out = sens.run(players, season, halves, base_cfg, sens_cfg, metrics_cfg)
    s = {"config_files": {"config/similarity.yaml": sim_fp, "config/sensitivity.yaml": sens_fp},
         "season": scope["season"]["season_name"],
         "settings": {"top_n": sens_cfg["views"]["top_n"], "top_k": sens_cfg["views"]["top_k"],
                      "robust_core_min_share": sens_cfg["robust_core"]["min_share_named_top_n"],
                      "tradeoff_metrics": sens_cfg["outputs"]["tradeoff_metrics"],
                      "figure_min_share": sens_cfg["outputs"]["figure_min_share"],
                      "draw_rank_quantiles": sens_cfg["outputs"]["draw_rank_quantiles"]},
         **sens.summarise(out, base_cfg, sens_cfg)}
    s["draws"].pop("reason", None)
    check_base(s, r4, sim_fp)
    s["run"] = {"seconds": round(time.time() - start, 1), "peak_rss_bytes": flatten.peak_rss_bytes()}
    s["figures"] = r5_figures.draw(s, sens_cfg["outputs"]["figure_min_share"], FIGURES)
    s["report_facts"] = report_r5.facts(s, report_r5.load_results())
    SUMMARY.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_r5.write_docs(s)   # renders from results/ r1-r4 and the summary just saved
    return s


if __name__ == "__main__":
    res = main()
    print(f"sensitivity config {res['config_files']['config/sensitivity.yaml']}")
    print("robust core:", res["robust_core"])
    print("recommendation:", [(p["name"], p["in_core"]) for p in res["recommendation"]])
