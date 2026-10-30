"""R6: render README.md from docs/templates/README.md with results/ only.

    python -m recruit.run_r6

The README reuses the R5 report context (report_r5.context and tables, the same figures as
docs/REPORT.md). The few figures only the README needs (download sizes in MB, recorded run times) are
derived here and saved to results/r6_readme.json, so every number in the README is in results/.
"""
from __future__ import annotations

import json

from recruit import config, report, report_r5

ROOT = config.ROOT
TEMPLATE = ROOT / "docs" / "templates" / "README.md"
README = ROOT / "README.md"
FACTS = ROOT / "results" / "r6_readme.json"

# Assumption rows: (label, value shown, config file, scenario-change prefixes that test it).
ASSUMPTIONS = [
    ("Minutes threshold (league minutes)", "min_minutes", "config/profiles.yaml, config/similarity.yaml", ["pool.min_minutes"]),
    ("Group weights (ball winning / progression / passing security / attacking output)", "group_weights",
     "config/similarity.yaml", ["group_weights"]),
    ("Value score (similarity / cheapness weights)", "value_weights", "config/similarity.yaml", ["value_score."]),
    ("Budget cap", "budget", "config/similarity.yaml", ["constraints.budget_cap_eur"]),
    ("Age range at the valuation date", "ages", "config/similarity.yaml", ["constraints.age_"]),
    ("Defensive metrics adjusted for possession", "adjusted", "config/profiles.yaml, config/similarity.yaml",
     ["possession_adjusted."]),
    ("Stale valuations (older than the gap line) flagged and kept", "stale", "config/matching.yaml, config/similarity.yaml",
     ["constraints.stale_valuations"]),
    ("Valuation date (latest value on or before it)", "valuation_date", "config/scope.yaml", ["valuation_date"]),
    ("Leicester City players excluded as targets", "excluded", "config/similarity.yaml", ["constraints.exclude_teams"]),
]


def readme_facts(r1: dict, r2: dict, r3: dict, r4: dict, r5: dict) -> dict:
    res = r1["gates"]["resource"]
    return {
        "statsbomb_raw_mb": round(res["statsbomb_raw_bytes"] / 1e6),
        "statsbomb_raw_files": res["statsbomb_raw_files"],
        "transfermarkt_raw_mb": round(res["transfermarkt_raw_bytes"] / 1e6, 1),
        "parquet_mb": round(res["parquet_bytes"] / 1e6),
        "flatten_peak_mb": round(res["flatten_peak_rss_bytes"] / 1e6),
        "max_peak_mb": round(max(res["flatten_peak_rss_bytes"], res["run_peak_rss_bytes"], r2["run"]["peak_rss_bytes"],
                                 r3["run"]["peak_rss_bytes"], r4["run"]["peak_rss_bytes"],
                                 r5["run"]["peak_rss_bytes"]) / 1e6),
        "seconds": {"r1_flatten": res["flatten_seconds"], "r2": r2["run"]["seconds"], "r3": r3["run"]["seconds"],
                    "r4": r4["run"]["seconds"], "r5": r5["run"]["seconds"]},
    }


def assumption_rows(r4: dict, r5: dict, valuation_date: str, stale_days: int) -> list[dict]:
    s = r4["settings"]
    shown = {"min_minutes": f"{r4['pool']['min_minutes']:,}",
             "group_weights": " / ".join(f"{w:.2f}" for w in s["group_weights"].values()),
             "value_weights": f"{s['value_weights']['similarity']:.1f} / {s['value_weights']['price']:.1f}",
             "budget": f"EUR {s['budget_cap_eur'] / 1e6:g}m", "ages": f"{s['age_min']}-{s['age_max']}",
             "adjusted": "yes", "stale": f"{stale_days} days", "valuation_date": valuation_date,
             "excluded": ", ".join(s["excluded_teams"])}
    rows = []
    for label, key, where, prefixes in ASSUMPTIONS:
        tested = [sc["label"] for sc in r5["scenarios"]
                  if any(k.startswith(p) for k in sc["changes"] for p in prefixes)]
        if key == "group_weights":
            tested.append(f"{r5['draws']['draws']} random weightings")
        rows.append({"label": label, "value": shown[key], "tested": "; ".join(tested) or "not varied", "where": where})
    return rows


def render() -> tuple[str, dict]:
    """The README text and the README-only facts, from results/ (nothing written)."""
    s = json.loads((ROOT / "results" / "r5_sensitivity.json").read_text(encoding="utf-8"))
    r = report_r5.load_results()
    f = s["report_facts"]
    facts = readme_facts(r["r1"], r["r2"], r["r3"], r["r4"], s)
    stale_days = r["r3"]["settings"]["max_gap_days"]
    ctx = report_r5.context(s, r, f) | report.publication_context(prefix="") | {
        "rm": facts, "stale_days": stale_days, "author": config.load("publication")["author"],
        "logo_source": config.load("publication")["statsbomb_logo"]["source_line"]}
    tables = report_r5.tables(s, r, f) | {"assumptions": report.markdown_table(
        assumption_rows(r["r4"], s, r["r1"]["valuation_date"], stale_days),
        [("label", "Assumption"), ("value", "Base case"), ("tested", "Tested in R5"), ("where", "Reason in")])}
    return report.render_template(TEMPLATE.read_text(encoding="utf-8"), ctx, tables), facts


def main() -> str:
    text, facts = render()
    FACTS.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    README.write_text(text, encoding="utf-8")
    print(f"wrote {README.relative_to(ROOT)} and {FACTS.relative_to(ROOT)}")
    return text


if __name__ == "__main__":
    main()
