"""R7 clean-clone check: clone the local main, rebuild R1-R6 from the existing raw files, compare.

    python -m recruit.clean_clone --workdir /some/empty/folder/outside/the/repo

Steps (config/reproducibility.yaml): git clone of this repository's main into <workdir>/clone; the
clone's committed results/, docs/ and README.md copied aside as the reference; fresh venv from
requirements.txt (+ pip install -e .; pip check); data/raw/ symlinked to the existing download; R1-R6
run in order, each under /usr/bin/time -l (seconds, max resident memory, macOS peak footprint); the
clone's tests (pytest, then pytest -m realdata); compare_runs on results/, docs/ and README.md; the
gitignored parquet files compared by sha256 with the working copy's. The record is written to
results/r7_clean_clone_check.json in this repository; run_r7 renders docs/R7_reproducibility.md from it.
Every date and timing sits under "run" (config/publication.yaml hindsight exemption).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from recruit import compare_runs, config

ROOT = config.ROOT
RECORD = ROOT / "results" / "r7_clean_clone_check.json"


def sh(cmd: list[str], cwd: Path, log: Path) -> str:
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n$ {' '.join(map(str, cmd))}\n")
        f.flush()
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        f.write(out.stdout + out.stderr)
    if out.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, cmd))} failed ({out.returncode}); see {log}")
    return out.stdout + out.stderr


def parse_time_l(text: str) -> dict:
    """/usr/bin/time -l (macOS): wall seconds, max resident set size (bytes), peak memory footprint (bytes)."""
    real = re.search(r"([\d.]+) real", text)
    rss = re.search(r"(\d+)\s+maximum resident set size", text)
    fp = re.search(r"(\d+)\s+peak memory footprint", text)
    return {"seconds": float(real.group(1)) if real else None,
            "max_resident_bytes": int(rss.group(1)) if rss else None,
            "peak_footprint_bytes": int(fp.group(1)) if fp else None}


def parse_pytest(text: str) -> dict:
    """Counts from pytest's last summary line ("193 passed, 2 skipped, 5 deselected in 6.1s") and the ids
    of failed tests (pytest -q prints a "FAILED <id> - <message>" line for each)."""
    line = [ln for ln in text.strip().splitlines() if ln.strip()][-1]
    counts = {k: 0 for k in ("passed", "failed", "skipped", "deselected", "errors")}
    for n, word in re.findall(r"(\d+) (passed|failed|skipped|deselected|errors?)", line):
        counts["errors" if word.startswith("error") else word] = int(n)
    failed = [ln.split()[1] for ln in text.splitlines() if ln.startswith(("FAILED ", "ERROR "))]
    return counts | {"summary": line.strip("= ").strip(), "failed_tests": failed}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def processed_hashes(working: Path, clone: Path, tol: dict) -> dict:
    """sha256 of every gitignored parquet file both trees hold under data/processed/ (one per file); a
    file that is not byte-identical is compared value by value (compare_runs.compare_parquet)."""
    out = {}
    for p in sorted(clone.rglob("*.parquet")):
        rel = p.relative_to(clone).as_posix()
        w = working / rel
        out[rel] = {"working_copy": sha256(w) if w.exists() else None, "clone": sha256(p)}
        if out[rel]["working_copy"] not in (None, out[rel]["clone"]):
            out[rel]["values"] = compare_runs.compare_parquet(w, p, tol)
    return out


def run(workdir: Path) -> dict:
    cfg = config.load("reproducibility")
    workdir = Path(workdir).resolve()
    if ROOT.resolve() in workdir.parents or workdir == ROOT.resolve():
        raise SystemExit("the workdir must be outside the repository")
    workdir.mkdir(parents=True, exist_ok=True)
    clone, ref, log = workdir / "clone", workdir / "reference", workdir / "check.log"
    if clone.exists():
        raise SystemExit(f"{clone} exists; use an empty workdir")
    t0, started = time.time(), datetime.now(timezone.utc).isoformat(timespec="seconds")

    sh(["git", "clone", "--branch", "main", str(ROOT), str(clone)], workdir, log)
    commit = sh(["git", "rev-parse", "HEAD"], clone, log).strip()
    clean = sh(["git", "status", "--porcelain"], clone, log).strip() == ""
    ref.mkdir()
    for t in cfg["clone"]["compare_folders"]:   # the committed files, before any step runs
        if (clone / t).is_dir():
            shutil.copytree(clone / t, ref / t)
        else:
            shutil.copy2(clone / t, ref / t)

    py = clone / ".venv" / "bin" / "python"
    sh([sys._base_executable, "-m", "venv", str(clone / ".venv")], clone, log)
    t_install = time.time()
    sh([str(py), "-m", "pip", "install", "-q", "-r", "requirements.txt"], clone, log)
    sh([str(py), "-m", "pip", "install", "-q", "-e", "."], clone, log)
    install_seconds = round(time.time() - t_install, 1)
    pip_check = sh([str(py), "-m", "pip", "check"], clone, log).strip()
    python_version = sh([str(py), "--version"], clone, log).strip()

    (clone / "data").mkdir(exist_ok=True)
    (clone / "data" / "raw").symlink_to(ROOT / "data" / "raw", target_is_directory=True)

    steps = []
    for step in cfg["clone"]["steps"]:
        out = sh(["/usr/bin/time", "-l", str(py), "-m", f"recruit.{step}"], clone, log)
        steps.append({"step": step} | parse_time_l(out))
        print(f"{step}: {steps[-1]['seconds']} s", flush=True)

    tests = {}
    for name, extra in (("unit", []), ("realdata", ["-m", "realdata"])):
        out = subprocess.run([str(py), "-m", "pytest", "-q", "-p", "no:cacheprovider", *extra], cwd=clone,
                             capture_output=True, text=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"\n$ pytest {' '.join(extra)}\n{out.stdout}{out.stderr}")
        tests[name] = parse_pytest(out.stdout) | {"exit_code": out.returncode}

    rows = compare_runs.compare_paths(ref, clone, cfg["clone"]["compare_folders"], cfg)
    record = {
        "clone": {"source": str(cfg["clone"]["source"]), "branch": "main", "commit": commit,
                  "clean_after_clone": clean, "raw_data": cfg["clone"]["raw_data"],
                  "steps_run": cfg["clone"]["steps"], "compare_folders": cfg["clone"]["compare_folders"]},
        "environment": {"python": python_version, "platform": f"{platform.system()} {platform.machine()}",
                        "pip_check": pip_check},
        "raw_fingerprints_checked_by_run_r1": True,
        "comparison": {"summary": compare_runs.summary(rows), "all_match": compare_runs.all_match(rows),
                       "files": rows},
        "processed_parquet_sha256": processed_hashes(ROOT / "data" / "processed", clone / "data" / "processed",
                                                     cfg["float_tolerance"]),
        "tests": tests,
        "run": {"started_utc": started, "total_seconds": round(time.time() - t0, 1),
                "install_seconds": install_seconds, "steps": steps},
    }
    RECORD.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {RECORD.relative_to(ROOT)}; all match: {record['comparison']['all_match']}")
    return record


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workdir", required=True)
    run(Path(ap.parse_args().workdir))


if __name__ == "__main__":
    main()
