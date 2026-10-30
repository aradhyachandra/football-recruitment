"""R7 renderer (src/recruit/run_r7.py) on a hand-made clean-clone record."""
import json

from recruit import run_r7


def record():
    files = [
        {"file": "results/r1.json", "status": "identical"},
        {"file": "results/r3.json", "status": "same_ignoring_run_time_fields", "ignored_paths": ["run"],
         "differing_paths": []},
        {"file": "results/r2.json", "status": "same_within_float_tolerance", "ignored_paths": ["run"],
         "differing_paths": [], "floats_within_tolerance": 12, "max_relative_difference": 2.2e-16},
        {"file": "docs/R1.md", "status": "same_except_run_time_lines",
         "changed_lines": [{"line": 9, "reference": "| Flatten time | 155.40 s |", "clone": "| Flatten time | 171.00 s |"}]},
        {"file": "README.md", "status": "identical"},
    ]
    from recruit.compare_runs import summary, all_match
    return {
        "clone": {"source": "local main", "branch": "main", "commit": "9015035abcdef", "clean_after_clone": True,
                  "raw_data": "symlink", "steps_run": ["run_r1"], "compare_folders": ["results", "docs", "README.md"]},
        "environment": {"python": "Python 3.13.5", "platform": "Darwin arm64", "pip_check": "No broken requirements found."},
        "comparison": {"summary": summary(files), "all_match": all_match(files), "files": files},
        "processed_parquet_sha256": {"data/processed/a.parquet": {"working_copy": "aa" * 32, "clone": "aa" * 32},
                                     "data/processed/b.parquet": {"working_copy": "bb" * 32, "clone": "cc" * 32}},
        "tests": {"unit": {"passed": 193, "failed": 0, "skipped": 0, "deselected": 0, "errors": 0,
                           "summary": "193 passed in 9.0s"},
                  "realdata": {"passed": 0, "failed": 0, "skipped": 0, "deselected": 193, "errors": 0,
                               "summary": "193 deselected in 1.0s"}},
        "run": {"started_utc": "2026-10-30T10:00:00+00:00", "total_seconds": 600.0, "install_seconds": 120.0,
                "steps": [{"step": "run_r1", "seconds": 300.5, "max_resident_bytes": 1_500_000_000,
                           "peak_footprint_bytes": 2_000_000_000},
                          {"step": "run_r2", "seconds": 12.0, "max_resident_bytes": 2_100_000_000,
                           "peak_footprint_bytes": 1_900_000_000}]},
    }


def test_render_from_hand_made_record(tmp_path):
    path = tmp_path / "rec.json"
    path.write_text(json.dumps(record()))
    text = run_r7.render(path)
    assert "{{" not in text
    assert "5 of 5 files match" in text and "2 of them byte-identical" in text
    assert "`9015035`" in text and "2026-10-30" in text
    assert "193 passed, 0 failed" in text
    assert "1 of 2 are byte-identical" in text and "`data/processed/b.parquet`" in text
    assert "2,100 MB resident (run_r2)" in text
    assert "10.00 minutes" in text and "312.50 seconds" in text  # report.fmt: floats to 2 decimals
    assert "Flatten time | 155.40 s |\" -> \"| Flatten time | 171.00 s |" in text
    assert "12 floats differ, by at most 2.2e-16" in text
    assert "Hudl StatsBomb logo" in text


def test_explain_for_a_real_difference():
    assert run_r7.explain({"status": "DIFFERENT", "differing_paths": ["shortlist.0"]}) == "Differs: `shortlist.0`."
    assert run_r7.explain({"status": "DIFFERENT"}) == "Differs: binary content."
    assert run_r7.explain({"status": "MISSING_IN_CLONE"}).startswith("The file exists on one side only")
