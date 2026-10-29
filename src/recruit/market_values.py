"""R3: join the R2 player profiles to transfermarkt-datasets players and their market values.

Steps (SQL in sql/r3_*.sql, name matching in matching.py):

    r3_club_map       config/club_map.yaml as a table, checked against match dates (r3_club_dates)
    r3_squads         Transfermarkt players with an appearance for each mapped club in the season window
    r3_sb_players     every StatsBomb spelling of each profiled player's name
    r3_matches        one row per StatsBomb player: matched Transfermarkt id (or why not), method, score
    r3_plausibility   StatsBomb matches vs Transfermarkt league appearances, per player and club
    r3_player_values  the joined table: profile keys, match, valuation on or before the date, age
"""
from __future__ import annotations

from recruit import config, matching

MATCH_COLUMNS = ["statsbomb_player_id", "transfermarkt_player_id", "method", "score", "status", "n_candidates",
                 "best_candidate_id", "best_candidate_name", "best_score", "second_score"]


def _sql(name: str) -> str:
    return (config.SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")


def _rows(con, sql: str, params=None) -> list[dict]:
    rel = con.execute(sql, params or {})
    cols = [d[0] for d in rel.description]
    return [dict(zip(cols, r)) for r in rel.fetchall()]


def load_club_map(con, scope: dict, club_map: dict) -> None:
    leagues = {c["competition_id"]: c["transfermarkt_id"] for c in scope["competitions"]}
    for key in ("statsbomb_team_id", "transfermarkt_club_id"):
        ids = [c[key] for c in club_map["clubs"]]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise ValueError(f"config/club_map.yaml: {key} {dup} listed more than once")
    con.execute("""CREATE OR REPLACE TABLE r3_club_map (statsbomb_team_id BIGINT, competition_id INTEGER,
                   transfermarkt_club_id BIGINT, transfermarkt_competition_id VARCHAR)""")
    con.executemany("INSERT INTO r3_club_map VALUES (?, ?, ?, ?)",
                    [[c["statsbomb_team_id"], c["competition_id"], c["transfermarkt_club_id"],
                      leagues[c["competition_id"]]] for c in club_map["clubs"]])


def check_club_map(con, scope: dict, club_map: dict, cfg: dict) -> list[dict]:
    """Every StatsBomb team in the data maps to exactly one club whose league dates match; stops otherwise."""
    load_club_map(con, scope, club_map)
    rows = _rows(con, _sql("r3_club_dates"))
    missing = [r["statsbomb_team_id"] for r in rows if r["transfermarkt_club_id"] is None]
    if missing:
        raise ValueError(f"StatsBomb teams {missing} are not in config/club_map.yaml")
    low = [r["statsbomb_team_id"] for r in rows
           if r["dates_covered"] / r["sb_matches"] < cfg["club_date_overlap_min"]]
    if low:
        raise ValueError(f"club map: date overlap below {cfg['club_date_overlap_min']} for StatsBomb teams {low}")
    return rows


def sb_players(con) -> list[dict]:
    return _rows(con, "SELECT player_id, names, nicknames, countries, team_ids FROM r3_sb_players ORDER BY player_id")


def squads(con) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for r in _rows(con, "SELECT * FROM r3_squads ORDER BY statsbomb_team_id, transfermarkt_player_id"):
        out.setdefault(r["statsbomb_team_id"], []).append({
            "player_id": r["transfermarkt_player_id"], "name": r["name"], "first_name": r["first_name"],
            "last_name": r["last_name"], "countries": [r["country_of_citizenship"], r["country_of_birth"]]})
    return out


def build(con, scope: dict, club_map: dict, overrides: dict, cfg: dict, log=lambda s: None) -> list[dict]:
    """Build every r3_* table; returns the club map check rows."""
    window = {"season_start": scope["season_window"]["start"], "season_end": scope["season_window"]["end"]}
    club_rows = check_club_map(con, scope, club_map, cfg)
    log(f"club map: {len(club_rows)} teams checked")
    con.execute(_sql("r3_squads"), window)
    con.execute(_sql("r3_sb_players"))
    outside = [o["transfermarkt_player_id"] for o in overrides["overrides"] if o.get("outside_squad")]
    known = {r[0] for r in con.execute("SELECT player_id FROM tm_players WHERE player_id IN (SELECT unnest(?))",
                                       [outside]).fetchall()}
    if set(outside) - known:
        raise ValueError(f"override: Transfermarkt players {sorted(set(outside) - known)} are not in tm_players")
    rows = matching.match_players(sb_players(con), squads(con), overrides["overrides"], cfg)
    log(f"matched {sum(r['transfermarkt_player_id'] is not None for r in rows)} of {len(rows)} players")
    con.execute("""CREATE OR REPLACE TABLE r3_matches (statsbomb_player_id BIGINT, transfermarkt_player_id BIGINT,
                   method VARCHAR, score DOUBLE, status VARCHAR, n_candidates INTEGER, best_candidate_id BIGINT,
                   best_candidate_name VARCHAR, best_score DOUBLE, second_score DOUBLE)""")
    con.executemany(f"INSERT INTO r3_matches VALUES ({', '.join('?' * len(MATCH_COLUMNS))})",
                    [[r[c] for c in MATCH_COLUMNS] for r in rows])
    con.execute(_sql("r3_plausibility"), {"max_gap": cfg["plausibility"]["max_abs_gap_matches"]})
    con.execute(_sql("r3_player_values"), {"valuation_date": scope["valuation_date"],
                                           "max_gap_days": cfg["valuation"]["max_gap_days"]})
    return club_rows
