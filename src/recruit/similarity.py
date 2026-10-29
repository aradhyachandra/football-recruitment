"""R4 maths: weighted Euclidean similarity on standardised metrics, cosine shape check, split-half
self-match ranks, the value-for-money frontier, shortlist constraints and the value score.

Pure functions on pandas frames (players as rows, metrics as columns); the settings come from
config/similarity.yaml and are passed in, never set here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def metric_weights(cfg: dict) -> dict[str, float]:
    """Metric weights adding up to 1: each group's weight split by the relative metric weights in it."""
    total = sum(g["weight"] for g in cfg["groups"])
    if not np.isclose(total, 1.0):
        raise ValueError(f"group weights add up to {total}, they must add up to 1")
    out = {}
    for g in cfg["groups"]:
        inner = sum(m["weight"] for m in g["metrics"])
        for m in g["metrics"]:
            out[m["name"]] = g["weight"] * m["weight"] / inner
    return out


def metric_groups(cfg: dict) -> dict[str, str]:
    return {m["name"]: g["name"] for g in cfg["groups"] for m in g["metrics"]}


def profile_matrix(long: pd.DataFrame, metrics: list[str], adjusted: set[str]) -> pd.DataFrame:
    """long: player_id, metric, value, value_padj. Adjusted metrics take value_padj, the rest value."""
    rows = long[long["metric"].isin(metrics)].copy()
    rows["x"] = np.where(rows["metric"].isin(adjusted), rows["value_padj"], rows["value"])
    X = rows.pivot(index="player_id", columns="metric", values="x").reindex(columns=metrics)
    if X.isna().any().any():
        raise ValueError(f"missing metric values for {int(X.isna().any(axis=1).sum())} players")
    return X.astype(float)


def standardise(X: pd.DataFrame, clip: float, ddof: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """z-scores within the rows given, clipped to +/-clip. Returns (Z, mask of clipped values)."""
    sd = X.std(ddof=ddof)
    if (sd == 0).any():
        raise ValueError(f"no spread in {list(sd[sd == 0].index)}")
    Z = (X - X.mean()) / sd
    return Z.clip(-clip, clip), Z.abs() > clip


def _w(Z: pd.DataFrame, w: dict) -> np.ndarray:
    return np.array([w[m] for m in Z.columns])


def distances(Z: pd.DataFrame, target, w: dict) -> pd.Series:
    """Weighted Euclidean distance of every row to the target row."""
    diff = Z - Z.loc[target]
    return pd.Series(np.sqrt((diff ** 2 * _w(Z, w)).sum(axis=1)), index=Z.index)


def similarity_score(d: pd.Series, clip: float) -> pd.Series:
    """100 * (1 - d / (2 * clip)): 100 = identical, 0 = the largest distance possible after clipping."""
    return 100 * (1 - d / (2 * clip))


def cosine(Z: pd.DataFrame, target, w: dict) -> pd.Series:
    """Cosine of the weighted z-vectors (sqrt(w) * z): profile shape relative to the pool average."""
    V = Z * np.sqrt(_w(Z, w))
    t = V.loc[target]
    return V.dot(t) / (np.linalg.norm(V, axis=1) * np.linalg.norm(t))


def group_gaps(Z: pd.DataFrame, target, w: dict, groups: dict) -> pd.DataFrame:
    """Per group, the weighted root-mean-square gap to the target in standard deviations."""
    diff2 = (Z - Z.loc[target]) ** 2 * _w(Z, w)
    out = {}
    for g in dict.fromkeys(groups.values()):
        cols = [m for m in Z.columns if groups[m] == g]
        out[g] = np.sqrt(diff2[cols].sum(axis=1) / sum(w[m] for m in cols))
    return pd.DataFrame(out, index=Z.index)


def percent_rank(s: pd.Series) -> pd.Series:
    """DuckDB percent_rank: (values strictly lower) / (n - 1); 0 for a single value."""
    n = len(s)
    lower = s.rank(method="min") - 1
    return lower / (n - 1) if n > 1 else lower * 0.0


def self_match_ranks(first: pd.DataFrame, second: pd.DataFrame, w: dict) -> pd.Series:
    """For each player, where his own second-half profile ranks among all second-half profiles by
    distance to his first-half profile (1 = closest). A tie counts against him."""
    if set(first.index) != set(second.index):
        raise ValueError("both halves must hold the same players")
    second = second.loc[first.index, first.columns]
    wv = _w(first, w)
    A, B = first.to_numpy(), second.to_numpy()
    D = np.sqrt((((A[:, None, :] - B[None, :, :]) ** 2) * wv).sum(axis=2))   # first i vs second j
    own = np.diag(D)
    others = D <= own[:, None]
    np.fill_diagonal(others, False)
    return pd.Series(1 + others.sum(axis=1), index=first.index)


def frontier(similarity: pd.Series, price: pd.Series) -> pd.Series:
    """True when no other player is at least as similar and at least as cheap, and better on one."""
    s, p = similarity.to_numpy(), price.to_numpy()
    dominated = ((s[None, :] >= s[:, None]) & (p[None, :] <= p[:, None])
                 & ((s[None, :] > s[:, None]) | (p[None, :] < p[:, None]))).any(axis=1)
    return pd.Series(~dominated, index=similarity.index)


def constraint_mask(df: pd.DataFrame, cons: dict) -> pd.DataFrame:
    """df: market_value_eur, age, team_ids (list). One column per constraint plus 'eligible'."""
    excluded = {t["statsbomb_team_id"] for t in cons["exclude_teams"]}
    value = df["market_value_eur"]
    m = pd.DataFrame(index=df.index)
    m["within_budget"] = value.notna() & (value <= cons["budget_cap_eur"])
    m["age_ok"] = df["age"].between(cons["age_min"], cons["age_max"])
    m["team_ok"] = df["team_ids"].map(lambda ids: not excluded & set(ids))
    m["eligible"] = m.all(axis=1)
    return m


def value_score(similarity: pd.Series, price: pd.Series, w_sim: float, w_price: float) -> pd.Series:
    """w_sim * similarity percentile + w_price * cheapness percentile, both 0-100 within the rows given."""
    if not np.isclose(w_sim + w_price, 1.0):
        raise ValueError("value-score weights must add up to 1")
    return 100 * (w_sim * percent_rank(similarity) + w_price * percent_rank(-price.astype(float)))


def rank_by_value(df: pd.DataFrame) -> list:
    """Index order by value score, ties broken by similarity (both descending)."""
    return list(df.sort_values(["value_score", "similarity"], ascending=False, kind="mergesort").index)
