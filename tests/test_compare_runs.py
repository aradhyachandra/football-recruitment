"""Clean-clone comparison (src/recruit/compare_runs.py) on hand-made folders."""
import json

import pytest

from recruit import compare_runs as cr

SETTINGS = {
    "run_time_keys": ["run", "seconds"],
    "float_tolerance": {"files": ["results/r2.json"], "relative": 1e-9, "absolute": 1e-12},
    "run_time_line_patterns": [r"\d s\b", r"\d MB\b"],
}


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        content = json.dumps(content, indent=2)
    path.write_bytes(content if isinstance(content, bytes) else content.encode())


def status(rows, name):
    return next(r for r in rows if r["file"] == name)


@pytest.fixture
def dirs(tmp_path):
    a, b = tmp_path / "ref", tmp_path / "clone"
    a.mkdir(), b.mkdir()
    return a, b


def test_identical_and_missing(dirs):
    a, b = dirs
    write(a, "results/x.json", {"k": 1})
    write(b, "results/x.json", {"k": 1})
    write(a, "docs/only_ref.md", "a")
    write(b, "docs/only_clone.md", "b")
    rows = cr.compare_paths(a, b, ["results", "docs"], SETTINGS)
    assert status(rows, "results/x.json")["status"] == "identical"
    assert status(rows, "docs/only_ref.md")["status"] == "MISSING_IN_CLONE"
    assert status(rows, "docs/only_clone.md")["status"] == "MISSING_IN_REFERENCE"


def test_json_run_time_keys_ignored_at_any_depth(dirs):
    a, b = dirs
    write(a, "results/r3.json", {"n": 5, "run": {"seconds": 8.0}, "g": {"seconds": {"r2": 1}, "keep": 2}})
    write(b, "results/r3.json", {"n": 5, "run": {"seconds": 9.1}, "g": {"seconds": {"r2": 3}, "keep": 2}})
    row = status(cr.compare_paths(a, b, ["results"], SETTINGS), "results/r3.json")
    assert row["status"] == "same_ignoring_run_time_fields"
    assert row["ignored_paths"] == ["g.seconds", "run"]
    assert row["differing_paths"] == []


def test_json_real_difference_is_reported(dirs):
    a, b = dirs
    write(a, "results/r4.json", {"shortlist": ["A", "B"], "run": {"seconds": 1}})
    write(b, "results/r4.json", {"shortlist": ["B", "A"], "run": {"seconds": 2}})
    row = status(cr.compare_paths(a, b, ["results"], SETTINGS), "results/r4.json")
    assert row["status"] == "DIFFERENT"
    assert row["differing_paths"] == ["shortlist.0", "shortlist.1"]


def test_float_tolerance_only_for_configured_files(dirs):
    a, b = dirs
    for name in ("results/r2.json", "results/r5.json"):
        write(a, name, {"m": 0.1 + 0.2, "i": 3})
        write(b, name, {"m": 0.3, "i": 3})      # differs at the 17th digit
    rows = cr.compare_paths(a, b, ["results"], SETTINGS)
    r2 = status(rows, "results/r2.json")
    assert r2["status"] == "same_within_float_tolerance"
    assert r2["max_relative_difference"] == pytest.approx(abs(0.1 + 0.2 - 0.3) / 0.3)
    assert status(rows, "results/r5.json")["status"] == "DIFFERENT"  # no tolerance elsewhere


def test_float_tolerance_does_not_hide_a_real_change(dirs):
    a, b = dirs
    write(a, "results/r2.json", {"m": 1.0})
    write(b, "results/r2.json", {"m": 1.001})
    assert status(cr.compare_paths(a, b, ["results"], SETTINGS), "results/r2.json")["status"] == "DIFFERENT"


def test_markdown_run_time_lines(dirs):
    a, b = dirs
    write(a, "docs/R1.md", "# R1\n| Flatten time | 155.40 s |\n| Peak | 362.27 MB |\nShortlist: A\n")
    write(b, "docs/R1.md", "# R1\n| Flatten time | 171.02 s |\n| Peak | 401.00 MB |\nShortlist: A\n")
    row = status(cr.compare_paths(a, b, ["docs"], SETTINGS), "docs/R1.md")
    assert row["status"] == "same_except_run_time_lines"
    assert [d["reference"] for d in row["changed_lines"]] == ["| Flatten time | 155.40 s |", "| Peak | 362.27 MB |"]


def test_markdown_other_changes_are_different(dirs):
    a, b = dirs
    write(a, "docs/R4.md", "| Flatten time | 155.40 s |\nShortlist: A\n")
    write(b, "docs/R4.md", "| Flatten time | 160.00 s |\nShortlist: B\n")
    assert status(cr.compare_paths(a, b, ["docs"], SETTINGS), "docs/R4.md")["status"] == "DIFFERENT"
    # a unit line whose words change is not a run-time difference either
    write(a, "docs/R5.md", "Flatten time 155.40 s\n")
    write(b, "docs/R5.md", "Load time 155.40 s\n")
    assert status(cr.compare_paths(a, b, ["docs"], SETTINGS), "docs/R5.md")["status"] == "DIFFERENT"
    # a different number of lines is a structural change
    write(a, "docs/R6.md", "a 1 s\n")
    write(b, "docs/R6.md", "a 1 s\nb 2 s\n")
    assert status(cr.compare_paths(a, b, ["docs"], SETTINGS), "docs/R6.md")["status"] == "DIFFERENT"


def test_binary_files_compared_byte_for_byte_and_single_file_target(dirs):
    a, b = dirs
    write(a, "docs/figures/f.png", b"\x89PNG1")
    write(b, "docs/figures/f.png", b"\x89PNG2")
    write(a, "README.md", "same\n")
    write(b, "README.md", "same\n")
    rows = cr.compare_paths(a, b, ["docs", "README.md"], SETTINGS)
    assert status(rows, "docs/figures/f.png")["status"] == "DIFFERENT"
    assert status(rows, "README.md")["status"] == "identical"
    assert all(r["sha256_reference"] and r["sha256_clone"] for r in rows)


def test_summary_counts():
    rows = [{"file": "results/a", "status": "identical"},
            {"file": "results/b", "status": "same_ignoring_run_time_fields"},
            {"file": "docs/c", "status": "DIFFERENT"}, {"file": "docs/d", "status": "MISSING_IN_CLONE"}]
    s = cr.summary(rows)
    assert s["results"] == {"files": 2, "identical": 1, "same_except_run_time": 1, "different": 0, "missing": 0,
                            "match": 2}
    assert s["docs"]["different"] == 1 and s["docs"]["missing"] == 1 and s["docs"]["match"] == 0
    assert cr.all_match(rows) is False and cr.all_match(rows[:2]) is True


def test_real_config_has_reasons():
    from recruit import config
    cfg = config.load("reproducibility")
    for key in ("run_time_keys", "float_tolerance", "run_time_line_patterns"):
        assert key in cfg
    assert cfg["float_tolerance"]["reason"] and cfg["run_time_keys_reason"] and cfg["run_time_line_patterns_reason"]
    assert cfg["float_tolerance"]["files"] == ["results/r2_profiles_summary.json"]


# ---------- clean_clone.py parsers ----------

def test_parse_time_l_macos_output():
    from recruit.clean_clone import parse_time_l
    text = ("r1 done\n      155.42 real       140.10 user         9.80 sys\n"
            "           380000000  maximum resident set size\n                   0  average shared memory size\n"
            "           412000000  peak memory footprint\n")
    assert parse_time_l(text) == {"seconds": 155.42, "max_resident_bytes": 380000000, "peak_footprint_bytes": 412000000}
    assert parse_time_l("nothing")["seconds"] is None


def test_parse_pytest_summary_line():
    from recruit.clean_clone import parse_pytest
    got = parse_pytest("....\n193 passed, 2 skipped, 1 deselected in 6.12s\n")
    assert (got["passed"], got["skipped"], got["deselected"], got["failed"]) == (193, 2, 1, 0)
    got = parse_pytest("FF\nFAILED tests/test_a.py::test_x - AssertionError: assert ['data/raw'] == []\n"
                       "===== 1 failed, 3 passed, 1 error in 2.0s =====\n")
    assert (got["failed"], got["passed"], got["errors"]) == (1, 3, 1)
    assert got["failed_tests"] == ["tests/test_a.py::test_x"]
    assert parse_pytest("\n196 deselected in 1.25s\n")["deselected"] == 196


def test_compare_parquet_float_noise_and_real_change(tmp_path):
    import pandas as pd
    tol = SETTINGS["float_tolerance"]
    a = pd.DataFrame({"player_id": [1, 2, 3], "metric": ["x", "y", "z"], "value": [0.1 + 0.2, 1.0, float("nan")]})
    b = a.iloc[[2, 0, 1]].copy()               # other row order
    b.loc[b["player_id"] == 1, "value"] = 0.3  # 17th-digit noise
    a.to_parquet(tmp_path / "a.parquet"), b.to_parquet(tmp_path / "b.parquet")
    got = cr.compare_parquet(tmp_path / "a.parquet", tmp_path / "b.parquet", tol)
    assert got["status"] == "same_within_float_tolerance" and 0 < got["max_relative_difference"] < 1e-15
    b.loc[b["player_id"] == 2, "value"] = 1.01
    b.to_parquet(tmp_path / "b.parquet")
    assert cr.compare_parquet(tmp_path / "a.parquet", tmp_path / "b.parquet", tol)["status"] == "DIFFERENT"
    b.loc[b["player_id"] == 2, ["value", "metric"]] = [1.0, "w"]
    b.to_parquet(tmp_path / "b.parquet")
    assert cr.compare_parquet(tmp_path / "a.parquet", tmp_path / "b.parquet", tol)["status"] == "DIFFERENT"
