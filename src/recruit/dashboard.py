"""Pure functions behind app/streamlit_app.py (no streamlit here, so they can be tested).

Reads results/ (committed summaries) and data/processed/ (built locally by R1-R3 from your own
download). No maths of its own: the Explore view builds a config with sensitivity.apply_changes and runs
run_r4.analyse, the same functions as R4 and R5. Every list is a similar profile under stated
assumptions, not a forecast of how a player would do at another club.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from recruit import config, run_r4, sensitivity

PUB = config.load("publication")


# ---------- loading ----------

def load_results(root: Path = config.ROOT) -> dict:
    files = {"r2": "r2_profiles_summary", "r4": "r4_shortlist", "r5": "r5_sensitivity"}
    return {k: json.loads((root / "results" / f"{v}.json").read_text(encoding="utf-8")) for k, v in files.items()}


def processed_available(processed: Path) -> bool:
    return all((processed / p).exists() for p in ("r2/r2_players.parquet", "r2/r2_player_season.parquet",
                                                  "r3/r3_player_values.parquet", "lineup_players"))


def load_inputs(processed: Path, scope: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The players and season tables run_r4.analyse expects, from the R1-R3 parquet files (the same
    columns run_r4.read_inputs takes from DuckDB)."""
    p = Path(processed)
    values = pd.read_parquet(p / "r3" / "r3_player_values.parquet",
                             columns=["player_id", "statsbomb_name", "minutes", "role", "main_competition_id", "age",
                                      "market_value_eur", "valuation_date", "valuation_stale"])
    teams = pd.read_parquet(p / "r2" / "r2_players.parquet", columns=["player_id", "teams"])
    team_names = dict(duckdb.sql(
        f"SELECT DISTINCT team_id, team_name FROM read_parquet('{(p / 'lineup_players').as_posix()}/*.parquet')").fetchall())
    leagues = {c["competition_id"]: c["name"] for c in scope["competitions"]}
    players = values.rename(columns={"statsbomb_name": "name"}).merge(teams, on="player_id")
    players["team_ids"] = players.pop("teams").map(lambda ts: [int(t["team_id"]) for t in ts])
    players["club"] = players["team_ids"].map(lambda ids: " / ".join(team_names[i] for i in ids))
    players["league"] = players["main_competition_id"].map(leagues)
    season = pd.read_parquet(p / "r2" / "r2_player_season.parquet", columns=["player_id", "metric", "value", "value_padj"])
    return players.sort_values("player_id").reset_index(drop=True), season


def selectable_players(players: pd.DataFrame, min_minutes: float) -> pd.DataFrame:
    """Players at or above the minutes threshold, with a unique label for the picker."""
    sel = players[players["minutes"] >= min_minutes].copy()
    sel["label"] = sel["name"] + " (" + sel["club"] + ", " + sel["role"] + ")"
    dup = sel["label"].duplicated(keep=False)
    sel.loc[dup, "label"] = sel.loc[dup, "label"] + " #" + sel.loc[dup, "player_id"].astype(str)
    return sel.sort_values("label").reset_index(drop=True)


# ---------- Explore: config and analysis (R4 functions) ----------

def normalise_weights(weights: dict) -> dict:
    """Group weights rescaled to add up to 1 (config/similarity.yaml: shares of the squared distance)."""
    total = float(sum(weights.values()))
    if total <= 0:
        raise ValueError("at least one group weight must be above 0")
    return {k: float(v) / total for k, v in weights.items()}


def explore_config(base: dict, player_id: int, role: str, team_ids: list, group_weights: dict | None = None,
                   budget_cap_eur: float | None = None, age_range: tuple | None = None) -> dict:
    """The R4 config with the selected player as target in his own role pool. Only the settings asked
    for change; the selected player's clubs replace the excluded teams (config/publication.yaml)."""
    changes = {"pool.role": role, "pool.target_statsbomb_player_id": int(player_id)}
    if PUB["dashboard"]["exclude_selected_players_clubs"]:
        changes["constraints.exclude_teams"] = [{"statsbomb_team_id": int(t), "name": "selected player's club"}
                                                for t in team_ids]
    if group_weights is not None:
        changes["group_weights"] = normalise_weights(group_weights)
    if budget_cap_eur is not None:
        changes["constraints.budget_cap_eur"] = budget_cap_eur
    if age_range is not None:
        changes["constraints.age_min"], changes["constraints.age_max"] = age_range
    return sensitivity.apply_changes(base, changes)


def explore(players: pd.DataFrame, season: pd.DataFrame, base_cfg: dict, metrics_cfg: dict, player_id: int,
            group_weights: dict | None = None, budget_cap_eur: float | None = None,
            age_range: tuple | None = None) -> dict:
    row = players.set_index("player_id").loc[player_id]
    cfg = explore_config(base_cfg, player_id, row["role"], list(row["team_ids"]), group_weights, budget_cap_eur,
                         age_range)
    res = run_r4.analyse(players, season, None, cfg, metrics_cfg, with_stability=False)
    return res | {"config": cfg}


# ---------- tables for display ----------

def _player_rows(t: pd.DataFrame, ids: list) -> pd.DataFrame:
    rows = t.loc[ids]
    stale = rows["valuation_stale"].map(lambda s: "no price" if pd.isna(s) else ("yes" if bool(s) else "no"))
    stale[rows["market_value_eur"].isna()] = "no price"
    return pd.DataFrame({
        "Player": rows["name"], "Club": rows["club"], "League": rows["league"],
        "Age": rows["age"].astype("Int64"), "Minutes": rows["minutes"].round().astype(int),
        "Market value (EUR m)": rows["market_value_eur"] / 1e6,
        "Valued on": rows["valuation_date"].map(lambda d: None if pd.isna(d) else str(d)[:10]),
        "Stale valuation": stale, "Similarity": rows["similarity"].round(1), "Cosine": rows["cosine"].round(2),
        "Similarity rank": rows["similarity_rank"].astype(int)}).reset_index(drop=True)


def similar_players(res: dict) -> pd.DataFrame:
    """The most similar candidates in the pool (no price or constraint filter), as in R4's top-similar list."""
    return _player_rows(res["table"], res["top_similar"])


def value_shortlist(res: dict) -> pd.DataFrame:
    """The value-for-money shortlist under the constraints (R4 value score and order)."""
    out = _player_rows(res["table"], res["shortlist"])
    out.insert(0, "Value rank", range(1, len(out) + 1))
    out["Value score"] = res["table"].loc[res["shortlist"], "value_score"].round(1).values
    out["On frontier"] = res["table"].loc[res["shortlist"], "on_frontier"].map(lambda x: bool(x == True)).values  # noqa: E712
    return out


def percentile_profile(res: dict, cfg: dict, metrics_cfg: dict) -> pd.DataFrame:
    """The selected player's key metrics: value, pool median and percentile (0-100) within his role pool,
    on the values used in the distance (possession-adjusted defence where configured)."""
    t = res["table"]
    target = t.index[t["is_target"]][0]
    labels = {m["name"]: m["label"] for m in metrics_cfg["metrics"] + metrics_cfg.get("ratios", [])}
    keys = cfg["percentiles"]["key_metrics"]
    return pd.DataFrame({"Metric": [labels.get(k, k) for k in keys],
                         "Value": [float(t.loc[target, f"value_{k}"]) for k in keys],
                         "Pool median": [float(t[f"value_{k}"].median()) for k in keys],
                         "Percentile": [100 * float(t.loc[target, f"pct_{k}"]) for k in keys],
                         "Possession-adjusted": [k in res["adjusted"] for k in keys]})


# ---------- Case view (results/ only, plus the R4 pool table when it exists) ----------

def case_profile(r2: dict) -> pd.DataFrame:
    """Kante's metrics against his role pool (results/r2_profiles_summary.json)."""
    rows = []
    for p in r2["departing_player"]["profile"]:
        adj = p["possession_adjusted"]
        rows.append({"Metric": p["label"], "Possession-adjusted": adj,
                     "Value": p["value_padj"] if adj else p["value"],
                     "Pool median": p["role_median_padj"] if adj else p["role_median"],
                     "Percentile": 100 * (p["pct_rank_padj"] if adj else p["pct_rank"])})
    return pd.DataFrame(rows)


def case_scatter_points(r4: dict, pool_table: pd.DataFrame | None) -> pd.DataFrame:
    """Similarity vs market value: the saved shortlist and frontier, plus the rest of the pool when the
    local R4 table (data/processed/r4/r4_similarity.parquet) is there."""
    rows, seen = [], set()
    short = {e["statsbomb_player_id"]: i + 1 for i, e in enumerate(r4["shortlist"])}
    front = {e["statsbomb_player_id"] for e in r4["frontier"]}
    for e in r4["shortlist"] + r4["frontier"]:
        pid = e["statsbomb_player_id"]
        if pid in seen:
            continue
        seen.add(pid)
        rows.append({"player_id": pid, "Player": e["name"], "Club": e["club"], "Age": e["age"],
                     "Similarity": e["similarity"], "Market value (EUR m)": e["market_value_eur"] / 1e6,
                     "Group": "Shortlist" if pid in short else "Frontier only", "Value rank": short.get(pid),
                     "On frontier": pid in front, "Stale valuation": bool(e["valuation_stale"])})
    if pool_table is not None:
        rest = pool_table[~pool_table["player_id"].isin(seen) & ~pool_table["is_target"]
                          & pool_table["market_value_eur"].notna()]
        for r in rest.itertuples():
            rows.append({"player_id": r.player_id, "Player": r.name, "Club": r.club, "Age": r.age,
                         "Similarity": round(float(r.similarity), 2), "Market value (EUR m)": r.market_value_eur / 1e6,
                         "Group": "Other pool players", "Value rank": None, "On frontier": False,
                         "Stale valuation": bool(r.valuation_stale == True)})  # noqa: E712
    out = pd.DataFrame(rows)
    other = out["Group"] == "Other pool players"
    return pd.concat([out[other], out[~other]], ignore_index=True)  # highlighted points drawn last, on top


def robust_core_table(r5: dict) -> pd.DataFrame:
    """The R5 robust core with how often each player stays near the top of the value ranking."""
    by_id = {c["statsbomb_player_id"]: c for c in r5["candidates"]}
    rec = {p["player_id"]: i + 1 for i, p in enumerate(r5["recommendation"])}
    s = r5["settings"]
    rows = []
    for pid in r5["robust_core"]:
        c = by_id[pid]
        vn, vd = c["value_named"], c["value_draws"]
        rows.append({"Player": c["name"], "Club": c["club"], "Age": c["age"],
                     "Market value (EUR m)": c["market_value_eur"] / 1e6, "R4 value rank": c.get("value_rank"),
                     f"Top {s['top_n']} share, scenarios": vn["share_top_n"],
                     f"Top {s['top_k']} share, scenarios": vn["share_top_k"],
                     f"Top {s['top_n']} share, draws": vd["share_top_n"],
                     "Median rank (scenarios)": vn["median_rank"],
                     "Rank range (scenarios)": f"{vn['min_rank']:g}-{vn['max_rank']:g}",
                     "Similarity rank": c["similarity_rank"],
                     "Recommendation": ("first choice" if rec.get(pid) == 1 else f"backup {rec[pid] - 1}")
                     if pid in rec else ""})
    out = pd.DataFrame(rows)
    order = [rec.get(pid, 99) for pid in r5["robust_core"]]
    return out.assign(_o=order).sort_values(["_o", "R4 value rank"], kind="mergesort").drop(columns="_o").reset_index(drop=True)


# ---------- display (config/publication.yaml dashboard) ----------

def money_label(eur: float) -> str:
    """Euros as the dashboard shows them: 10_000_000 -> "EUR 10m", 500_000 -> "EUR 0.5m"."""
    return f"EUR {eur / 1e6:g}m"


def budget_options(slider: dict) -> list[int]:
    """Every budget the slider offers, in euros (min to max in steps)."""
    return list(range(int(slider["min"]), int(slider["max"]) + 1, int(slider["step"])))


def display_columns(kind: str, df: pd.DataFrame) -> list[str]:
    """The columns shown for one table: all but the ones hidden in config (data behind it unchanged)."""
    hide = set(PUB["dashboard"]["table_hide"][kind])
    return [c for c in df.columns if c not in hide]


def short_labels() -> dict:
    return dict(PUB["dashboard"]["short_labels"])
