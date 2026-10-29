"""Download the published StatsBomb Open Data and transfermarkt-datasets files (no scraping).

Resumable: a file already on disk is skipped. Polite: a small delay between requests. Each file is
written to <name>.part and renamed only when complete, so an interrupted run leaves no broken file.

    python -m recruit.download            # both sources
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Callable

from recruit import config

USER_AGENT = "football-recruitment-research/0.1 (non-commercial portfolio project)"


def _urlopen_bytes(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_to_file(url: str, dest: Path, fetch: Callable = _urlopen_bytes, retries: int = 4,
                  backoff: float = 2.0, timeout: float = 60, sleep: Callable = time.sleep) -> bool:
    """Download url to dest. Returns False if dest already existed (skipped), True if fetched.
    Retries `retries` times, waiting backoff, 2*backoff, 4*backoff ... seconds."""
    dest = Path(dest)
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries + 1):
        try:
            data = fetch(url, timeout)
            break
        except OSError:
            if attempt == retries:
                raise
            sleep(backoff * 2 ** attempt)
    part = dest.with_name(dest.name + ".part")
    part.write_bytes(data)
    part.replace(dest)
    return True


def download_statsbomb(base_url: str, raw_dir: Path, season_id: int, competition_ids: list[int],
                       delay: float = 0.2, sleep: Callable = time.sleep, log: Callable = lambda s: None,
                       **fetch_kw) -> dict:
    """competitions.json, matches/<comp>/<season>.json, then events/ and lineups/ for every listed match."""
    raw_dir = Path(raw_dir)
    counts = {"downloaded": 0, "skipped": 0, "matches": 0}

    def get(rel: str) -> None:
        fetched = fetch_to_file(f"{base_url}/{rel}", raw_dir / rel, sleep=sleep, **fetch_kw)
        counts["downloaded" if fetched else "skipped"] += 1
        if fetched and delay:
            sleep(delay)

    get("competitions.json")
    for cid in competition_ids:
        rel = f"matches/{cid}/{season_id}.json"
        get(rel)
        match_ids = [m["match_id"] for m in json.loads((raw_dir / rel).read_text(encoding="utf-8"))]
        for i, mid in enumerate(match_ids, 1):
            get(f"events/{mid}.json")
            get(f"lineups/{mid}.json")
            if i % 50 == 0:
                log(f"competition {cid}: {i}/{len(match_ids)} matches")
        counts["matches"] += len(match_ids)
    return counts


def download_transfermarkt(base_url: str, raw_dir: Path, tables: list[str], delay: float = 0.2,
                           sleep: Callable = time.sleep, **fetch_kw) -> dict:
    counts = {"downloaded": 0, "skipped": 0}
    for t in tables:
        fetched = fetch_to_file(f"{base_url}/{t}.csv.gz", Path(raw_dir) / f"{t}.csv.gz", sleep=sleep,
                                **fetch_kw)
        counts["downloaded" if fetched else "skipped"] += 1
        if fetched and delay:
            sleep(delay)
    return counts


def main() -> None:
    data = config.load("data")
    scope = config.load("scope")
    d = data["download"]
    kw = {"retries": d["retries"], "backoff": d["backoff_seconds"], "timeout": d["timeout_seconds"]}
    tm = download_transfermarkt(data["transfermarkt"]["base_url"], config.ROOT / data["transfermarkt"]["raw_dir"],
                                data["transfermarkt"]["tables"], delay=d["delay_seconds"], **kw)
    print("transfermarkt:", tm, flush=True)
    sb = download_statsbomb(data["statsbomb"]["base_url"], config.ROOT / data["statsbomb"]["raw_dir"],
                            scope["season"]["season_id"], config.competition_ids(scope),
                            delay=d["delay_seconds"], log=lambda s: print(s, flush=True), **kw)
    print("statsbomb:", sb, flush=True)


if __name__ == "__main__":
    main()
