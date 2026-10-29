"""Flatten StatsBomb JSON (events, lineups, matches) to parquet, one match at a time.

Only the fields listed in config/statsbomb_fields.yaml are kept. Each competition gets one parquet
file per table, written row group by row group, so at most one match is in memory at a time. The
peak memory of the step (resident set size) is saved for the R1 audit.

    python -m recruit.flatten
"""
from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from recruit import config

ARROW_TYPES = {"string": pa.string(), "int32": pa.int32(), "int64": pa.int64(),
               "float64": pa.float64(), "bool": pa.bool_()}
MATCH_KEYS = [("match_id", pa.int64()), ("competition_id", pa.int32())]
STATS_FILE = "flatten_stats.json"


def _get(record, path: str):
    node = record
    for part in path.split("."):
        if isinstance(node, list):
            idx = int(part)
            node = node[idx] if idx < len(node) else None
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
        if node is None:
            return None
    return node


def extract(record: dict, spec: list[dict]) -> dict:
    """One flat dict from one JSON record: first present path per field, else the field's default."""
    out = {}
    for f in spec:
        paths = f["path"] if isinstance(f["path"], list) else [f["path"]]
        value = None
        for p in paths:
            value = _get(record, str(p))
            if value is not None:
                break
        out[f["name"]] = f.get("default") if value is None else value
    return out


def schema(spec: list[dict], keys=MATCH_KEYS) -> pa.Schema:
    return pa.schema([pa.field(n, t) for n, t in keys] +
                     [pa.field(f["name"], ARROW_TYPES[f["type"]]) for f in spec])


def _table(rows: list[dict], spec: list[dict], keys=MATCH_KEYS) -> pa.Table:
    return pa.Table.from_pylist(rows, schema=schema(spec, keys))


def events_table(events: list[dict], match_id: int, competition_id: int, spec: list[dict]) -> pa.Table:
    rows = [{"match_id": match_id, "competition_id": competition_id, **extract(e, spec)} for e in events]
    return _table(rows, spec)


def lineup_tables(lineups: list[dict], match_id: int, competition_id: int, player_spec: list[dict],
                  position_spec: list[dict]) -> tuple[pa.Table, pa.Table]:
    """One row per player in the squad list; one row per position stint (team_id, player_id added)."""
    keys = {"match_id": match_id, "competition_id": competition_id}
    players, positions = [], []
    for team in lineups:
        for p in team["lineup"]:
            players.append({**keys, **extract({**p, "team_id": team["team_id"],
                                               "team_name": team["team_name"]}, player_spec)})
            for pos in p.get("positions") or []:
                positions.append({**keys, "team_id": team["team_id"], "player_id": p["player_id"],
                                  **extract(pos, position_spec)})
    pos_keys = MATCH_KEYS + [("team_id", pa.int64()), ("player_id", pa.int64())]
    return _table(players, player_spec), _table(positions, position_spec, pos_keys)


def peak_rss_bytes() -> int:
    """Peak resident memory of this process so far (macOS reports bytes, Linux kilobytes)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)


def flatten_all(raw_dir: Path, out_dir: Path, season_id: int, competition_ids: list[int],
                fields: dict, log=lambda s: None) -> dict:
    """Rebuild all parquet files under out_dir from the raw JSON. Returns counts and peak memory."""
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    start = time.time()
    match_rows = []
    n_events = n_matches = 0
    for kind in ("events", "lineup_players", "lineup_positions"):
        (out_dir / kind).mkdir(parents=True, exist_ok=True)
    pos_keys = MATCH_KEYS + [("team_id", pa.int64()), ("player_id", pa.int64())]
    for cid in competition_ids:
        matches = json.loads((raw_dir / f"matches/{cid}/{season_id}.json").read_text(encoding="utf-8"))
        match_rows += [extract(m, fields["matches"]) for m in matches]
        name = f"competition_{cid}.parquet"
        with pq.ParquetWriter(out_dir / "events" / name, schema(fields["events"])) as ev_w, \
             pq.ParquetWriter(out_dir / "lineup_players" / name, schema(fields["lineup_players"])) as pl_w, \
             pq.ParquetWriter(out_dir / "lineup_positions" / name,
                              schema(fields["lineup_positions"], pos_keys)) as po_w:
            for i, m in enumerate(matches, 1):
                mid = m["match_id"]
                with open(raw_dir / f"events/{mid}.json", encoding="utf-8") as fh:
                    ev = events_table(json.load(fh), mid, cid, fields["events"])
                with open(raw_dir / f"lineups/{mid}.json", encoding="utf-8") as fh:
                    pl, po = lineup_tables(json.load(fh), mid, cid, fields["lineup_players"],
                                           fields["lineup_positions"])
                ev_w.write_table(ev)
                pl_w.write_table(pl)
                po_w.write_table(po)
                n_events += ev.num_rows
                n_matches += 1
                if i % 100 == 0:
                    log(f"competition {cid}: {i}/{len(matches)} matches flattened")
    pq.write_table(_table(match_rows, fields["matches"], keys=[]), out_dir / "matches.parquet")
    return {"matches": n_matches, "events": n_events, "seconds": round(time.time() - start, 1),
            "peak_rss_bytes": peak_rss_bytes()}


def main() -> dict:
    data = config.load("data")
    scope = config.load("scope")
    out_dir = config.ROOT / data["processed_dir"]
    stats = flatten_all(config.ROOT / data["statsbomb"]["raw_dir"], out_dir, scope["season"]["season_id"],
                        config.competition_ids(scope), config.load("statsbomb_fields"),
                        log=lambda s: print(s, flush=True))
    (out_dir / STATS_FILE).write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    return stats


if __name__ == "__main__":
    print(main())
