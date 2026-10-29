"""Load the flattened StatsBomb parquet and the transfermarkt-datasets CSVs into DuckDB.

Column types are explicit: StatsBomb tables are created from config/statsbomb_fields.yaml (the same
types the flatten step writes), transfermarkt tables from sql/r1_tm_tables.sql. CSVs are read as text
and cast on insert, so a value that does not fit its type stops the load instead of becoming NULL.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from recruit import config

DUCKDB_TYPES = {"string": "VARCHAR", "int32": "INTEGER", "int64": "BIGINT", "float64": "DOUBLE",
                "bool": "BOOLEAN"}
MATCH_KEYS = [("match_id", "BIGINT"), ("competition_id", "INTEGER")]
POSITION_KEYS = MATCH_KEYS + [("team_id", "BIGINT"), ("player_id", "BIGINT")]
SB_TABLES = {  # duckdb table: (parquet location under processed_dir, field list, key columns)
    "sb_matches": ("matches.parquet", "matches", []),
    "sb_events": ("events/*.parquet", "events", MATCH_KEYS),
    "sb_lineup_players": ("lineup_players/*.parquet", "lineup_players", MATCH_KEYS),
    "sb_lineup_positions": ("lineup_positions/*.parquet", "lineup_positions", POSITION_KEYS),
}
TM_TABLES = ["players", "player_valuations", "clubs", "appearances"]


def connect(path, memory_limit: str, threads: int) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(path))
    con.execute(f"SET memory_limit = '{memory_limit}'")
    con.execute(f"SET threads = {int(threads)}")
    return con


def create_sql(table: str, spec: list[dict], keys: list[tuple]) -> str:
    cols = [f"{n} {t}" for n, t in keys]
    cols += [f"{f['name']} {f.get('duckdb_type', DUCKDB_TYPES[f['type']])}" for f in spec]
    return f"CREATE TABLE {table} (\n    " + ",\n    ".join(cols) + "\n)"


def load_statsbomb(con, processed_dir: Path, fields: dict) -> None:
    for table, (location, kind, keys) in SB_TABLES.items():
        con.execute(create_sql(table, fields[kind], keys))
        con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM "
                    f"read_parquet('{(Path(processed_dir) / location).as_posix()}')")


def load_transfermarkt(con, paths: dict[str, Path]) -> None:
    """paths: table name (players, ...) -> CSV file (gzipped or plain)."""
    con.execute((config.SQL_DIR / "r1_tm_tables.sql").read_text(encoding="utf-8"))
    for t in TM_TABLES:
        cols = [r[0] for r in con.execute(f"DESCRIBE tm_{t}").fetchall()]
        con.execute(f"INSERT INTO tm_{t} BY NAME SELECT {', '.join(cols)} FROM "
                    f"read_csv('{Path(paths[t]).as_posix()}', header=true, all_varchar=true)")


def row_counts(con) -> dict[str, int]:
    return {t: int(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
            for t in list(SB_TABLES) + [f"tm_{t}" for t in TM_TABLES]}
