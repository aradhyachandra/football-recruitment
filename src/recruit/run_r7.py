"""R7: render docs/R7_reproducibility.md from results/r7_clean_clone_check.json (the clean-clone
check's own record, written by recruit.clean_clone). Formats saved values only.

    python -m recruit.run_r7
"""
from __future__ import annotations

import json
from pathlib import Path

from recruit import compare_runs, config, report

ROOT = config.ROOT
RECORD = ROOT / "results" / "r7_clean_clone_check.json"
TEMPLATE = ROOT / "docs" / "templates" / "R7_reproducibility.md"
DOC = ROOT / "docs" / "R7_reproducibility.md"


def explain(row: dict) -> str:
    """What differs in one file that is not byte-identical, from the comparison row alone."""
    s = row["status"]
    if s == "same_ignoring_run_time_fields":
        return "Only run-time fields differ: " + ", ".join(f"`{p}`" for p in row["ignored_paths"]) + "."
    if s == "same_within_float_tolerance":
        return (f"{row['floats_within_tolerance']:,} floats differ, by at most {row['max_relative_difference']:.1e} "
                "relative (inside the configured tolerance); run-time fields: "
                + ", ".join(f"`{p}`" for p in row["ignored_paths"]) + ".")
    if s == "same_except_run_time_lines":
        return (f"{len(row['changed_lines'])} line(s) differ, each only in run-time numbers: "
                + "; ".join(f"line {d['line']}: \"{d['reference'].strip()}\" -> \"{d['clone'].strip()}\""
                            for d in row["changed_lines"]))
    if s.startswith("MISSING"):
        return "The file exists on one side only."
    paths = row.get("differing_paths") or [f"line {d['line']}" for d in row.get("changed_lines", [])]
    return "Differs: " + (", ".join(f"`{p}`" for p in paths[:10]) if paths else "binary content") + "."


def context(rec: dict) -> tuple[dict, dict]:
    rows = rec["comparison"]["files"]
    summ = rec["comparison"]["summary"]
    folder_rows = [{"f": k if k == "README.md" else f"{k}/", **v} for k, v in summ.items()]
    not_identical = [{"f": f"`{r['file']}`", "s": r["status"], "why": explain(r)} for r in rows
                     if r["status"] != "identical"]
    steps = rec["run"]["steps"]
    step_rows = [{"s": s["step"], "sec": s["seconds"], "rss": round(s["max_resident_bytes"] / 1e6),
                  "fp": round(s["peak_footprint_bytes"] / 1e6)} for s in steps]
    parquet = rec["processed_parquet_sha256"]
    same_parquet = [k for k, v in parquet.items() if v["working_copy"] == v["clone"]]
    other_parquet = [{"f": f"`{k}`", "w": f"`{(v['working_copy'] or 'missing')[:16]}`", "c": f"`{v['clone'][:16]}`",
                      "rows": v.get("values", {}).get("rows"), "s": v.get("values", {}).get("status", "not compared"),
                      "gap": f"{v['values']['max_relative_difference']:.1e}" if "values" in v else ""}
                     for k, v in parquet.items() if v["working_copy"] != v["clone"]]
    explained = config.load("reproducibility").get("explained_test_failures", {})
    failures = [{"t": f"`{f}`", "why": explained.get(f, "not explained")}
                for suite in ("unit", "realdata") for f in rec["tests"][suite].get("failed_tests", [])]
    t = rec["tests"]
    facts = {
        "files": len(rows), "match": sum(r["status"] in compare_runs.MATCH for r in rows),
        "identical": sum(r["status"] == "identical" for r in rows),
        "results_files": summ.get("results", {}).get("files", 0), "results_match": summ.get("results", {}).get("match", 0),
        "results_identical": summ.get("results", {}).get("identical", 0),
        "all_match": "yes" if rec["comparison"]["all_match"] else "NO",
        "steps_seconds": round(sum(s["seconds"] for s in steps), 1),
        "peak_rss_mb": round(max(s["max_resident_bytes"] for s in steps) / 1e6),
        "peak_fp_mb": round(max(s["peak_footprint_bytes"] for s in steps) / 1e6),
        "peak_step": max(steps, key=lambda s: s["max_resident_bytes"])["step"],
        "total_minutes": round(rec["run"]["total_seconds"] / 60, 1),
        "install_minutes": round(rec["run"]["install_seconds"] / 60, 1),
        "parquet_files": len(parquet), "parquet_same": len(same_parquet),
        "unit": t["unit"], "realdata": t["realdata"],
        "commit": rec["clone"]["commit"][:7], "date": rec["run"]["started_utc"][:10],
        "clean": "yes" if rec["clone"]["clean_after_clone"] else "NO",
    }
    tables = {
        "folders": report.markdown_table(folder_rows, [
            ("f", "Folder"), ("files", "Files"), ("identical", "Byte-identical"),
            ("same_except_run_time", "Same except run-time fields"), ("different", "Different"),
            ("missing", "Missing on one side")]),
        "not_identical": report.markdown_table(not_identical, [("f", "File"), ("s", "Result"), ("why", "What differs")])
        if not_identical else "None: every file is byte-identical.",
        "steps": report.markdown_table(step_rows, [("s", "Step"), ("sec", "Seconds"),
                                                   ("rss", "Max resident memory (MB)"), ("fp", "macOS peak footprint (MB)")]),
        "parquet_other": report.markdown_table(other_parquet, [
            ("f", "File"), ("w", "Working copy"), ("c", "Clone"), ("rows", "Rows"), ("s", "Values"),
            ("gap", "Largest relative gap")]) if other_parquet else "None.",
        "failures": report.markdown_table(failures, [("t", "Failed test"), ("why", "Explanation")])
        if failures else "None.",
    }
    return {"r": rec, "t": facts, "cfg": config.load("reproducibility")} | report.publication_context(), tables


def render(record: Path = RECORD, template: Path = TEMPLATE) -> str:
    rec = json.loads(Path(record).read_text(encoding="utf-8"))
    ctx, tables = context(rec)
    return report.render_template(Path(template).read_text(encoding="utf-8"), ctx, tables)


def main() -> None:
    DOC.write_text(render(), encoding="utf-8")
    print(f"wrote {DOC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
