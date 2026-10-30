"""R1 data audit: per-league counts and the four gates. Queries live in sql/r1_*.sql.

Each gate returns a dict with its numbers and `passed`; thresholds come from config/audit.yaml.
"""
from __future__ import annotations

from recruit import config


def _query(con, name: str, params: dict | None = None) -> list[dict]:
    rel = con.execute((config.SQL_DIR / f"{name}.sql").read_text(encoding="utf-8"), params or {})
    cols = [d[0] for d in rel.description]
    return [dict(zip(cols, row)) for row in rel.fetchall()]


def _names(scope: dict) -> dict[int, str]:
    return {c["competition_id"]: c["name"] for c in scope["competitions"]}


def league_summary(con, scope: dict) -> list[dict]:
    names = _names(scope)
    rows = _query(con, "r1_league_summary", {"competition_ids": list(names)})
    return [{"competition_id": r["competition_id"], "league": names[r["competition_id"]],
             **{k: int(v) for k, v in r.items() if k != "competition_id"}} for r in rows]


def event_type_counts(con, scope: dict) -> list[dict]:
    """One row per event type: a count per league plus the total, most frequent type first."""
    names = _names(scope)
    by_type: dict[str, dict] = {}
    for r in _query(con, "r1_event_types"):
        row = by_type.setdefault(r["type_name"], {"type_name": r["type_name"],
                                                  **{n: 0 for n in names.values()}, "total": 0})
        row[names[r["competition_id"]]] += int(r["n"])
        row["total"] += int(r["n"])
    return sorted(by_type.values(), key=lambda r: (-r["total"], r["type_name"]))


def valuation_gate(con, scope: dict, cfg: dict) -> dict:
    g = cfg["valuation_gate"]
    params = {"leagues": [c["transfermarkt_id"] for c in scope["competitions"]],
              "season_start": scope["season_window"]["start"], "season_end": scope["season_window"]["end"],
              "valuation_date": scope["valuation_date"], "months": g["window_months"]}
    rows = _query(con, "r1_valuation_gate", params)
    total, by_league = rows[-1], rows[:-1]

    def shares(r):
        n = int(r["players"])
        return {"players": n, "with_valuation_before": int(r["with_valuation_before"]),
                "share_before": r["with_valuation_before"] / n if n else 0.0}

    history = _query(con, "r1_departing_valuations",
                     {"player_id": scope["departing_player_ids"]["transfermarkt_player_id"],
                      "valuation_date": scope["valuation_date"], "months": g["history_months"],
                      "window_months": g["window_months"]})
    usable = [h for h in history if h["usable"]]
    latest = usable[-1] if usable else None
    departing = {
        "transfermarkt_player_id": scope["departing_player_ids"]["transfermarkt_player_id"],
        "latest_before": None if latest is None else {
            "date": latest["date"].isoformat(), "market_value_eur": int(latest["market_value_in_eur"]),
            "days_before": int(latest["days_before"])},
        "history": [{"date": h["date"].isoformat(), "market_value_eur": int(h["market_value_in_eur"]),
                     "club": h["current_club_name"], "days_before": int(h["days_before"])} for h in history],
    }
    out = {**shares(total), "by_league": [{"league": r["league"], **shares(r)} for r in by_league],
           "window_months": g["window_months"], "min_share_before": g["min_share_before"],
           "departing_player": departing}
    out["passed"] = bool(out["share_before"] >= g["min_share_before"]
                         and (latest is not None or not g["departing_player_required"]))
    return out


def pressure_gate(con, scope: dict, cfg: dict) -> dict:
    names = _names(scope)
    rows = _query(con, "r1_pressure_gate", {"competition_ids": list(names),
                                            "event_type": cfg["pressure_gate"]["event_type"]})
    by_league = [{"league": names[r["competition_id"]], "pressure_events": int(r["pressure_events"]),
                  "matches": int(r["matches"]), "matches_with_pressure": int(r["matches_with_pressure"])}
                 for r in rows]
    present = {r["league"] for r in by_league if r["pressure_events"] > 0}
    return {"by_league": by_league, "passed": present == set(names.values())}


def lineup_gate(con, scope: dict, cfg: dict) -> dict:
    r = {k: int(v) if v is not None else None for k, v in _query(con, "r1_lineup_gate")[0].items()}
    r["share_from_time"] = r["with_from_time"] / r["position_rows"] if r["position_rows"] else 0.0
    r["open_ended_by_end_reason"] = [{"end_reason": o["end_reason"], "rows": int(o["rows"])}
                                     for o in _query(con, "r1_lineup_open_ended")]
    r["min_share_from_time"] = cfg["lineup_gate"]["min_share_from_time"]
    r["passed"] = bool(r["position_rows"] > 0 and r["share_from_time"] >= r["min_share_from_time"]
                       and r["matches_with_both_teams"] == r["matches"])
    return r


def resource_gate(flatten_stats: dict, sizes: dict, cfg: dict) -> dict:
    peak_gb = flatten_stats["peak_rss_bytes"] / 2**30
    limit = cfg["resource_gate"]["max_peak_rss_gb"]
    return {**sizes, "flatten_peak_rss_bytes": flatten_stats["peak_rss_bytes"], "peak_rss_gb": peak_gb,
            "flatten_seconds": flatten_stats["seconds"], "max_peak_rss_gb": limit,
            "passed": bool(peak_gb <= limit)}


def departing_player_statsbomb(con, scope: dict) -> list[dict]:
    rows = _query(con, "r1_departing_statsbomb", {"name": scope["departing_player"]["statsbomb_name"]})
    return [{**r, "player_id": int(r["player_id"]), "matches_listed": int(r["matches_listed"]),
             "matches_played": int(r["matches_played"])} for r in rows]
