"""Compare a clean clone's rebuilt files with the committed ones (R7, docs/R7_reproducibility.md).

    python -m recruit.compare_runs <reference dir> <clone dir> [--out file.json]

Rules (config/reproducibility.yaml, each with a reason):
- every file must be byte-identical, except that
- JSON files may differ in run-time fields (run_time_keys, at any depth), and the files listed under
  float_tolerance may differ in floats within that tolerance;
- markdown files may differ only in lines that carry a run-time unit (s, MB, GB) and are identical to
  the committed line once every number is masked.
Every ignored path and changed line is kept in the output, so every difference can be reviewed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from recruit import config

NUMBER = re.compile(r"\d[\d,]*(\.\d+)?")
TEXT_SUFFIXES = {".md", ".txt"}
MATCH = ("identical", "same_ignoring_run_time_fields", "same_within_float_tolerance", "same_except_run_time_lines")


# ---------- JSON ----------

def strip_run_time(obj, keys: set):
    if isinstance(obj, dict):
        return {k: strip_run_time(v, keys) for k, v in obj.items() if k not in keys}
    if isinstance(obj, list):
        return [strip_run_time(v, keys) for v in obj]
    return obj


def run_time_paths(obj, keys: set, path: str = "") -> list[str]:
    """Paths of run-time fields present in obj."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            out += [p] if k in keys else run_time_paths(v, keys, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += run_time_paths(v, keys, f"{path}.{i}" if path else str(i))
    return out


def json_differences(a, b, path: str = "", tol: dict | None = None, worst: list | None = None) -> list[str]:
    """Dotted paths at which two parsed JSON values differ. With tol, two floats count as equal when
    math.isclose(rel_tol, abs_tol) holds; the largest relative gap seen is kept in worst[0]."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in list(a) + [k for k in b if k not in a]:
            p = f"{path}.{k}" if path else str(k)
            out += json_differences(a[k], b[k], p, tol, worst) if k in a and k in b else [p]
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b))
                for d in json_differences(x, y, f"{path}.{i}" if path else str(i), tol, worst)]
    if (tol is not None and isinstance(a, float) and isinstance(b, float) and a != b
            and math.isclose(a, b, rel_tol=tol["relative"], abs_tol=tol["absolute"])):
        if worst is not None:
            worst[0] = max(worst[0], abs(a - b) / max(abs(a), abs(b)))
        return []
    return [] if a == b else [path]


def compare_json(x: bytes, y: bytes, keys: set, tol: dict | None) -> dict:
    jx, jy = json.loads(x), json.loads(y)
    sx, sy = strip_run_time(jx, keys), strip_run_time(jy, keys)
    row = {"ignored_paths": sorted(set(run_time_paths(jx, keys)) | set(run_time_paths(jy, keys)))}
    exact = json_differences(sx, sy)
    if not exact:
        row["status"], row["differing_paths"] = "same_ignoring_run_time_fields", []
        return row
    worst = [0.0]
    diff = json_differences(sx, sy, tol=tol, worst=worst) if tol else exact
    row["differing_paths"] = diff
    if diff:
        row["status"] = "DIFFERENT"
    else:
        row["status"] = "same_within_float_tolerance"
        row["floats_within_tolerance"] = len(exact)
        row["max_relative_difference"] = worst[0]
    return row


# ---------- markdown ----------

def compare_text(x: bytes, y: bytes, patterns: list[str]) -> dict:
    a, b = x.decode("utf-8").splitlines(), y.decode("utf-8").splitlines()
    if len(a) != len(b):
        return {"status": "DIFFERENT", "changed_lines": [], "note": f"{len(a)} lines v {len(b)}"}
    changed = [{"line": i + 1, "reference": la, "clone": lb} for i, (la, lb) in enumerate(zip(a, b)) if la != lb]
    ok = all(any(re.search(p, d["reference"]) for p in patterns)
             and NUMBER.sub("#", d["reference"]) == NUMBER.sub("#", d["clone"]) for d in changed)
    return {"status": "same_except_run_time_lines" if ok and changed else "DIFFERENT", "changed_lines": changed}


# ---------- folders ----------

def _files(root: Path, targets: list[str]) -> set[str]:
    out = set()
    for t in targets:
        p = root / t
        if p.is_file():
            out.add(t)
        elif p.is_dir():
            out |= {q.relative_to(root).as_posix() for q in p.rglob("*")
                    if q.is_file() and q.name != ".DS_Store" and "__pycache__" not in q.parts}
    return out


def compare_paths(reference, clone, targets: list[str], settings: dict) -> list[dict]:
    """One row per file under targets (folders or single files) in either tree."""
    reference, clone = Path(reference), Path(clone)
    a, b = _files(reference, targets), _files(clone, targets)
    keys = set(settings["run_time_keys"])
    tol_files = set(settings["float_tolerance"]["files"])
    rows = []
    for name in sorted(a | b):
        row = {"file": name}
        if name not in b:
            row["status"] = "MISSING_IN_CLONE"
        elif name not in a:
            row["status"] = "MISSING_IN_REFERENCE"
        else:
            x, y = (reference / name).read_bytes(), (clone / name).read_bytes()
            if x == y:
                row["status"] = "identical"
            elif name.endswith(".json"):
                row |= compare_json(x, y, keys, settings["float_tolerance"] if name in tol_files else None)
            elif Path(name).suffix in TEXT_SUFFIXES:
                row |= compare_text(x, y, settings["run_time_line_patterns"])
            else:
                row["status"] = "DIFFERENT"
        for side, root, names in (("reference", reference, a), ("clone", clone, b)):
            row[f"sha256_{side}"] = hashlib.sha256((root / name).read_bytes()).hexdigest() if name in names else None
        rows.append(row)
    return rows


def summary(rows: list[dict]) -> dict:
    """Counts per top-level folder (README.md counts as its own entry)."""
    out = {}
    for r in rows:
        top = r["file"].split("/")[0]
        s = out.setdefault(top, {"files": 0, "identical": 0, "same_except_run_time": 0, "different": 0, "missing": 0})
        s["files"] += 1
        if r["status"] == "identical":
            s["identical"] += 1
        elif r["status"] in MATCH:
            s["same_except_run_time"] += 1
        elif r["status"].startswith("MISSING"):
            s["missing"] += 1
        else:
            s["different"] += 1
    for s in out.values():
        s["match"] = s["identical"] + s["same_except_run_time"]
    return out


def all_match(rows: list[dict]) -> bool:
    return all(r["status"] in MATCH for r in rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("reference")
    ap.add_argument("clone")
    ap.add_argument("--out")
    args = ap.parse_args()
    cfg = config.load("reproducibility")
    rows = compare_paths(args.reference, args.clone, cfg["clone"]["compare_folders"], cfg)
    for r in rows:
        print(f"{r['status']:<32} {r['file']}")
    print(f"{len(rows)} files, {sum(r['status'] in MATCH for r in rows)} match")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()


# ---------- parquet values (gitignored files, compared after the sha256 check) ----------

def compare_parquet(first, second, tol: dict) -> dict:
    """Two parquet files with the same columns and rows (in any row order): non-float columns must be
    equal; float columns within the tolerance. Returns the status and the largest relative gap."""
    import numpy as np
    import pandas as pd

    a, b = pd.read_parquet(first), pd.read_parquet(second)
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return {"status": "DIFFERENT", "reason": "columns or row count differ"}
    floats = [c for c in a.columns if pd.api.types.is_float_dtype(a[c])]
    keys = [c for c in a.columns if c not in floats and a[c].map(lambda v: isinstance(v, (str, int, np.integer))).all()]
    if keys:
        a, b = (x.sort_values(keys, kind="mergesort").reset_index(drop=True) for x in (a, b))
    others = [c for c in a.columns if c not in floats]
    if not a[others].astype(str).equals(b[others].astype(str)):
        return {"status": "DIFFERENT", "reason": "non-float values differ"}
    worst, ok = 0.0, True
    for c in floats:
        x, y = a[c].to_numpy(float), b[c].to_numpy(float)
        same_nan = np.isnan(x) == np.isnan(y)
        m = ~np.isnan(x) & ~np.isnan(y)
        close = np.isclose(x[m], y[m], rtol=tol["relative"], atol=tol["absolute"])
        ok &= bool(same_nan.all() and close.all())
        scale = np.maximum(np.abs(x[m]), np.abs(y[m]))
        gap = np.abs(x[m] - y[m])[scale > 0] / scale[scale > 0]
        worst = max(worst, float(gap.max()) if gap.size else 0.0)
    return {"status": "same_within_float_tolerance" if ok else "DIFFERENT", "float_columns": len(floats),
            "rows": len(a), "max_relative_difference": worst}
