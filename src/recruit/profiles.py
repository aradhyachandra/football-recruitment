"""R2: player-season profiles. The preparation is SQL (sql/r2_*.sql) run here in order:

    r2_events          event columns R2 needs, time in seconds, derived flags (progressive, regains, ...)
    r2_period_lengths  real period lengths (added time included)
    r2_stints          minutes per lineup position spell, with role bucket
    r2_team_possession possession share per team and match (in-play time; pass share as a check)
    r2_player_match    per player, match and metric: raw value and possession-adjusted value
    r2_player_season   one row per player (all clubs summed) and per-90 values per metric

Metric definitions, roles and parameters come from config/metrics.yaml, roles.yaml and profiles.yaml;
they are loaded into small DuckDB tables (r2_metric_defs, r2_ratio_defs, r2_roles) that the SQL joins.
"""
from __future__ import annotations

from recruit import config

BUILD_STEPS = ["r2_events", "r2_period_lengths", "r2_stints", "r2_team_possession", "r2_player_match",
               "r2_player_season"]
VALUES = {"count", "shot_xg"}       # what a metric may sum (see sql/r2_player_match.sql)
FLAGS = {"progressive", "into_final_third", "pressure_regain", "key_pass", "ball_recovery_failure"}
FILTER_LISTS = ["subtypes", "exclude_subtypes", "outcomes", "exclude_outcomes", "flags_true", "flags_false"]


def load_configs() -> dict:
    return {name: config.load(name) for name in ("profiles", "metrics", "roles")}


def _query(con, name: str, params: dict | None = None) -> list[dict]:
    rel = con.execute((config.SQL_DIR / f"{name}.sql").read_text(encoding="utf-8"), params or {})
    cols = [d[0] for d in rel.description]
    return [dict(zip(cols, row)) for row in rel.fetchall()]


def _run(con, name: str, params: dict | None = None) -> None:
    con.execute((config.SQL_DIR / f"{name}.sql").read_text(encoding="utf-8"), params or {})


def metric_def_rows(metrics_cfg: dict) -> list[list]:
    """One row per metric for r2_metric_defs; refuses values and flags the SQL does not know."""
    out = []
    for i, m in enumerate(metrics_cfg["metrics"]):
        value = m.get("value", "count")
        if value not in VALUES:
            raise ValueError(f"metric {m['name']}: value must be one of {sorted(VALUES)}, not {value!r}")
        unknown = set(m.get("flags_true", []) + m.get("flags_false", [])) - FLAGS
        if unknown:
            raise ValueError(f"metric {m['name']}: unknown flags {sorted(unknown)}")
        out.append([i, m["name"], m["label"], m["event_type"], *[m.get(k) for k in FILTER_LISTS],
                    bool(m.get("outcome_null", False)), value, bool(m.get("possession_adjusted", False)),
                    bool(m.get("in_profile", True))])
    return out


def load_config_tables(con, metrics_cfg: dict, roles_cfg: dict) -> None:
    lists = ", ".join(f"{k} VARCHAR[]" for k in FILTER_LISTS)
    con.execute(f"""CREATE OR REPLACE TABLE r2_metric_defs (sort_order INTEGER, name VARCHAR, label VARCHAR,
                    event_type VARCHAR, {lists}, outcome_null BOOLEAN, value VARCHAR,
                    possession_adjusted BOOLEAN, in_profile BOOLEAN)""")
    con.executemany(f"INSERT INTO r2_metric_defs VALUES ({', '.join('?' * (len(FILTER_LISTS) + 8))})",
                    metric_def_rows(metrics_cfg))
    con.execute("CREATE OR REPLACE TABLE r2_ratio_defs (name VARCHAR, label VARCHAR, numerator VARCHAR, "
                "denominator VARCHAR)")
    con.executemany("INSERT INTO r2_ratio_defs VALUES (?, ?, ?, ?)",
                    [[r["name"], r["label"], r["numerator"], r["denominator"]] for r in metrics_cfg["ratios"]])
    con.execute("CREATE OR REPLACE TABLE r2_roles (position_id INTEGER, role VARCHAR, role_order INTEGER)")
    con.executemany("INSERT INTO r2_roles VALUES (?, ?, ?)",
                    [[p, r["name"], i] for i, r in enumerate(roles_cfg["roles"]) for p in r["positions"]])


def build(con, scope: dict, cfg: dict, log=lambda s: None) -> None:
    """Run every R2 preparation step; the tables stay in the DuckDB connection."""
    prof, flags = cfg["profiles"], cfg["metrics"]["flags"]
    excluded = prof["possession"]["excluded_event_types"]
    cids = config.competition_ids(scope)
    load_config_tables(con, cfg["metrics"], cfg["roles"])
    params = {
        "r2_events": {"competition_ids": cids, "excluded_event_types": excluded,
                      "max_backward_seconds": prof["event_timestamps"]["max_backward_seconds"],
                      "regain_seconds": flags["pressure_regain_seconds"],
                      "pass_excluded_subtypes": flags["progressive"]["pass_excluded_subtypes"],
                      "min_share_closer": flags["progressive"]["min_share_closer"],
                      "min_distance": flags["progressive"]["min_distance"],
                      "final_third_x": flags["final_third_x"]},
        "r2_stints": {"competition_ids": cids,
                      "clock_starts": prof["match_clock"]["period_clock_start_seconds"]},
        "r2_team_possession": {"excluded_event_types": excluded},
        "r2_player_match": {"reference_share": prof["possession_adjustment"]["reference_opponent_share"]},
    }
    for step in BUILD_STEPS:
        log(f"running sql/{step}.sql")
        _run(con, step, params.get(step))


# --- summaries (no per-player rows except the departing player's own profile) -------------------------

def _league_names(scope: dict) -> dict[int, str]:
    return {c["competition_id"]: c["name"] for c in scope["competitions"]}


def pool_sizes(con, scope: dict, cfg: dict) -> list[dict]:
    names = _league_names(scope)
    rows = _query(con, "r2_pool_sizes", {"thresholds": cfg["profiles"]["minutes"]["sensitivity_thresholds"]})
    return [{"threshold": int(r["threshold"]), "role": r["role"], "league": names[r["competition_id"]],
             "players": int(r["players"])} for r in rows]


def distributions(con, cfg: dict) -> list[dict]:
    qs = cfg["profiles"]["distribution_percentiles"]
    keys = [f"p{round(q * 100)}" for q in qs]
    rows = _query(con, "r2_distributions", {"percentiles": qs,
                                            "threshold": cfg["profiles"]["minutes"]["threshold"]})

    def named(values):
        return None if values is None or all(v is None for v in values) else dict(zip(keys, values))

    return [{"role": r["role"], "metric": r["metric"], "kind": r["kind"], "players": int(r["players"]),
             "value": named(r["value_q"]), "value_padj": named(r["value_padj_q"])} for r in rows]


def departing_profile(con, scope: dict, cfg: dict) -> list[dict]:
    return _query(con, "r2_departing_profile",
                  {"player_id": scope["departing_player_ids"]["statsbomb_player_id"],
                   "threshold": cfg["profiles"]["minutes"]["threshold"]})


def departing_player(con, scope: dict) -> dict:
    pid = scope["departing_player_ids"]["statsbomb_player_id"]
    p = _query_sql(con, "SELECT * FROM r2_players WHERE player_id = ?", [pid])[0]
    p["roles"] = _query_sql(con, "SELECT role, minutes FROM r2_player_roles WHERE player_id = ? "
                                 "ORDER BY minutes DESC", [pid])
    p["avg_team_share"] = con.execute(
        "SELECT sum(team_share * minutes) / sum(minutes) FROM r2_player_match "
        "WHERE player_id = ? AND metric = (SELECT min(name) FROM r2_metric_defs)", [pid]).fetchone()[0]
    p["positions"] = _query_sql(con, "SELECT position_id, sum(minutes) AS minutes FROM r2_stints "
                                     "WHERE player_id = ? GROUP BY position_id ORDER BY minutes DESC", [pid])
    return p


def _query_sql(con, sql: str, params: list) -> list[dict]:
    rel = con.execute(sql, params)
    cols = [d[0] for d in rel.description]
    return [dict(zip(cols, row)) for row in rel.fetchall()]


def possession_check(con) -> dict:
    return _query(con, "r2_possession_check")[0]


def team_minutes_check(con, cfg: dict) -> dict:
    return _query(con, "r2_team_minutes", {"tolerance": cfg["profiles"]["team_minutes_check"]["tolerance_share"]})[0]


def checks(con, cfg: dict) -> dict:
    return _query(con, "r2_checks", {"threshold": cfg["profiles"]["minutes"]["threshold"]})[0]
