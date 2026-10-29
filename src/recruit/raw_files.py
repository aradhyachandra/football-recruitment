"""Fingerprints of the raw files (sha256, sizes, row counts), so a changed download is caught.

transfermarkt-datasets: one entry per table file. StatsBomb has thousands of small files, so they are
grouped (competitions, then matches / events / lineups per competition); a group's sha256 is the
sha256 of its sorted "relative path  file sha256" lines, so changing any one file changes it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import yaml

HEADER = ("# Fingerprints of the raw files as downloaded in R1 (python -m recruit.run_r1 --record).\n"
          "# Every run stops if a file no longer matches. Do not edit by hand.\n")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def csv_data_rows(path: Path) -> int:
    """Data rows of a (gzipped) CSV as DuckDB parses it, so quoted line breaks are not miscounted."""
    return int(duckdb.sql(f"SELECT COUNT(*) FROM read_csv('{Path(path).as_posix()}', header=true, "
                          "all_varchar=true)").fetchone()[0])


def fingerprint_transfermarkt(raw_dir: Path, tables: list[str], suffix: str = ".csv.gz",
                              count_rows: bool = True) -> dict:
    out = {}
    for t in tables:
        p = Path(raw_dir) / f"{t}{suffix}"
        out[t] = {"file": p.name, "sha256": sha256_file(p), "bytes": p.stat().st_size}
        if count_rows:
            out[t]["data_rows"] = csv_data_rows(p)
    return out


def _group(raw_dir: Path, rels: list[str], count_records: bool) -> dict:
    lines, size, records = [], 0, 0
    for rel in sorted(rels):
        p = raw_dir / rel
        lines.append(f"{rel}  {sha256_file(p)}\n")
        size += p.stat().st_size
        if count_records:
            with open(p, encoding="utf-8") as fh:
                records += len(json.load(fh))  # one file at a time keeps memory low
    out = {"files": len(rels), "bytes": size,
           "sha256": hashlib.sha256("".join(lines).encode()).hexdigest()}
    if count_records:
        out["records"] = records
    return out


def fingerprint_statsbomb(raw_dir: Path, season_id: int, competition_ids: list[int],
                          count_records: bool = True) -> dict:
    raw_dir = Path(raw_dir)
    out = {"competitions": _group(raw_dir, ["competitions.json"], count_records)}
    for cid in competition_ids:
        rel = f"matches/{cid}/{season_id}.json"
        ids = [m["match_id"] for m in json.loads((raw_dir / rel).read_text(encoding="utf-8"))]
        out[f"matches_{cid}"] = _group(raw_dir, [rel], count_records)
        for kind in ("events", "lineups"):
            out[f"{kind}_{cid}"] = _group(raw_dir, [f"{kind}/{m}.json" for m in ids], count_records)
    return out


def write_fingerprints(fp: dict, out: Path) -> None:
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(HEADER)
        yaml.safe_dump(fp, fh, sort_keys=True)


def read_fingerprints(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def verify(sb_dir: Path, tm_dir: Path, season_id: int, competition_ids: list[int], tables: list[str],
           expected: dict, suffix: str = ".csv.gz") -> None:
    """Raise ValueError if any raw file or file group differs from the recorded fingerprint."""
    current = {"statsbomb": fingerprint_statsbomb(sb_dir, season_id, competition_ids, count_records=False),
               "transfermarkt": fingerprint_transfermarkt(tm_dir, tables, suffix, count_rows=False)}
    problems = []
    for source, groups in current.items():
        for key, got in groups.items():
            want = expected.get(source, {}).get(key)
            if want is None:
                problems.append(f"{source}/{key}: no recorded fingerprint")
            elif any(got[k] != want[k] for k in got):
                problems.append(f"{source}/{key}: sha256 {got['sha256'][:12]}... != recorded "
                                f"{want['sha256'][:12]}...")
    if problems:
        raise ValueError("Raw files do not match config/raw_files.yaml:\n  " + "\n  ".join(problems))
