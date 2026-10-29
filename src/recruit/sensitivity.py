"""R5 sensitivity: run the R4 analysis under one-change scenarios and random group weights, count how
often each candidate stays near the top, define the robust core and apply the recommendation rule.

Pure functions on pandas frames; every setting comes from config/sensitivity.yaml and the R4 base
config/similarity.yaml, both passed in.
"""
from __future__ import annotations

import copy
import hashlib
import json

import numpy as np
import pandas as pd

from recruit import run_r4


# ---------- scenario configs ----------

def apply_changes(base: dict, changes: dict) -> dict:
    """A copy of the base config with the changes applied. Keys are dotted paths into the config, or
    `group_weights` (every group named, nothing else). An unknown key raises, so a typo cannot pass
    silently as the base case."""
    cfg = copy.deepcopy(base)
    for path, value in changes.items():
        if path == "group_weights":
            names = [g["name"] for g in cfg["groups"]]
            if set(value) != set(names):
                raise KeyError(f"group_weights must name exactly {names}")
            for g in cfg["groups"]:
                g["weight"] = float(value[g["name"]])
            continue
        *parents, leaf = path.split(".")
        node = cfg
        for p in parents:
            node = node[p]
        if leaf not in node:
            raise KeyError(f"unknown setting {path}")
        node[leaf] = value
    return cfg


def config_fingerprint(cfg: dict) -> str:
    """sha256 of the effective config (keys sorted), so each scenario's settings can be identified.
    Keys are turned into text first: YAML reads a bare `on:` key as the boolean True."""
    def text_keys(x):
        if isinstance(x, dict):
            return {str(k): text_keys(v) for k, v in x.items()}
        return [text_keys(v) for v in x] if isinstance(x, list) else x
    return hashlib.sha256(json.dumps(text_keys(cfg), sort_keys=True, default=str).encode()).hexdigest()


def dirichlet_group_weights(base: dict, draws: int, seed: int, concentration: float) -> list[dict]:
    """Group weights drawn from Dirichlet(concentration x base weights), in the config's group order."""
    names = [g["name"] for g in base["groups"]]
    alpha = concentration * np.array([g["weight"] for g in base["groups"]])
    W = np.random.default_rng(seed).dirichlet(alpha, size=draws)
    return [dict(zip(names, map(float, row))) for row in W]


# ---------- running ----------

def ranks(res: dict) -> pd.DataFrame:
    """One row per candidate of one analysis: value rank (eligible only), similarity rank and score."""
    t = res["table"]
    t = t[~t["is_target"]]
    return pd.DataFrame({"value_rank": t["value_rank"].astype(float), "similarity_rank": t["similarity_rank"],
                         "similarity": t["similarity"]})


def run(players, season, halves, base_cfg: dict, sens_cfg: dict, metrics_cfg: dict) -> dict:
    named, fingerprints, results = {}, {}, {}
    for s in sens_cfg["scenarios"]:
        cfg = apply_changes(base_cfg, s["changes"])
        res = run_r4.analyse(players, season, halves, cfg, metrics_cfg, with_stability=s["id"] == "base")
        named[s["id"]] = ranks(res)
        fingerprints[s["id"]] = config_fingerprint(cfg)
        results[s["id"]] = res
    rw = sens_cfg["random_weights"]
    weights = dirichlet_group_weights(base_cfg, rw["draws"], rw["seed"], rw["concentration"])
    draws = [ranks(run_r4.analyse(players, season, halves, apply_changes(base_cfg, {"group_weights": w}),
                                  metrics_cfg, with_stability=False)) for w in weights]
    return {"named": named, "draws": draws, "draw_weights": weights, "fingerprints": fingerprints,
            "base": results["base"], "results": results}


# ---------- robustness ----------

def robustness(frames: dict | list, col: str, top_n: int, top_k: int,
               quantiles: tuple = (0.05, 0.95)) -> pd.DataFrame:
    """Per player over the scenarios given: share in the top n and top k (a scenario where he has no
    rank counts as outside), median / min / max rank and the 5th-95th percentile over the scenarios
    where he is ranked (lower and upper quantile from config, saved as p05_rank / p95_rank), the number
    of those, and his median similarity score."""
    frames = list(frames.values()) if isinstance(frames, dict) else list(frames)
    R = pd.concat([f[col] for f in frames], axis=1)
    S = pd.concat([f["similarity"] for f in frames], axis=1)
    n = len(frames)
    out = pd.DataFrame(index=R.index)
    out["scenarios"] = n
    out["ranked"] = R.notna().sum(axis=1)
    out["share_top_n"] = (R <= top_n).sum(axis=1) / n
    out["share_top_k"] = (R <= top_k).sum(axis=1) / n
    out["median_rank"] = R.median(axis=1)
    out["min_rank"] = R.min(axis=1)
    out["max_rank"] = R.max(axis=1)
    out["p05_rank"] = R.quantile(quantiles[0], axis=1)
    out["p95_rank"] = R.quantile(quantiles[1], axis=1)
    out["median_similarity"] = S.median(axis=1)
    return out


def robust_core(rob: pd.DataFrame, min_share: float) -> list:
    """Players in the top n in at least min_share of the scenarios, by the recommendation order."""
    core = rob[rob["share_top_n"] >= min_share - 1e-12].index
    return [p["player_id"] for p in recommend(rob.loc[core], list(core), count=len(core))]


def recommend(rob: pd.DataFrame, core: list, count: int) -> list[dict]:
    """Core players by share in the top k, ties by median similarity (both descending); if the core has
    fewer than `count`, the rest by share in the top n, then top k, then median similarity."""
    order = rob.loc[list(core)].sort_values(["share_top_k", "median_similarity"], ascending=False,
                                            kind="mergesort")
    picks = [{"player_id": pid, "in_core": True} for pid in order.index[:count]]
    if len(picks) < count:
        rest = rob.drop(index=list(core)).sort_values(["share_top_n", "share_top_k", "median_similarity"],
                                                      ascending=False, kind="mergesort")
        picks += [{"player_id": pid, "in_core": False} for pid in rest.index[:count - len(picks)]]
    return picks


# ---------- summary ----------

def _num(x, digits=3):
    if x is None or pd.isna(x):
        return None
    x = float(x)
    return int(x) if x.is_integer() else round(x, digits)


def _rob_dict(rob: pd.DataFrame, pid) -> dict:
    if pid not in rob.index:
        return {"share_top_n": 0.0, "share_top_k": 0.0, "ranked": 0}
    r = rob.loc[pid]
    return {k: _num(r[k]) for k in ("scenarios", "ranked", "share_top_n", "share_top_k", "median_rank",
                                     "min_rank", "max_rank", "p05_rank", "p95_rank", "median_similarity")}


def summarise(run_out: dict, base_cfg: dict, sens_cfg: dict) -> dict:
    """Summaries only: per-scenario top lists, robustness for the saved candidates, core, recommendation."""
    v, rc, out_cfg = sens_cfg["views"], sens_cfg["recommendation"], sens_cfg["outputs"]
    n, k = v["top_n"], v["top_k"]
    named = run_out["named"]
    sim_ids = [s["id"] for s in sens_cfg["scenarios"] if s["kind"] in v["similarity_view_kinds"]]
    q = tuple(out_cfg["draw_rank_quantiles"])
    rob = {"value_named": robustness(named, "value_rank", n, k, q),
           "value_draws": robustness(run_out["draws"], "value_rank", n, k, q),
           "similarity_named": robustness({i: named[i] for i in sim_ids}, "similarity_rank", n, k, q),
           "similarity_draws": robustness(run_out["draws"], "similarity_rank", n, k, q)}
    core = robust_core(rob["value_named"], sens_cfg["robust_core"]["min_share_named_top_n"])
    picks = recommend(rob["value_named"], core, rc["count"])

    sc = out_cfg["saved_candidates"]
    keep = set(rob["value_named"].index[(rob["value_named"]["share_top_n"] * len(named)).round() >= sc["min_named_top_n"]])
    keep |= set(rob["similarity_named"].index[(rob["similarity_named"]["share_top_n"] * len(sim_ids)).round()
                                              >= sc["min_named_top_n"]])
    keep |= set(rob["value_draws"].index[rob["value_draws"]["share_top_n"] >= sc["min_draw_top_n_share"]])

    t = run_out["base"]["table"]
    keys = base_cfg["percentiles"]["key_metrics"]
    groups = [g["name"] for g in base_cfg["groups"]]
    target = base_cfg["pool"]["target_statsbomb_player_id"]
    cands = []
    for pid in keep:
        # base-case figures; a player outside the base pool (for example only at 600 minutes) is described
        # from the first scenario that has him
        src = t if pid in t.index else next(r["table"] for r in run_out["results"].values() if pid in r["table"].index)
        e = run_r4.entry(src, pid, keys, groups)
        e["in_base_pool"] = pid in t.index
        e["in_core"] = pid in core
        e["named_value_ranks"] = {i: _num(f["value_rank"].get(pid)) for i, f in named.items()}
        e["named_similarity_ranks"] = {i: _num(named[i]["similarity_rank"].get(pid)) for i in sim_ids}
        for view, r in rob.items():
            e[view] = _rob_dict(r, pid)
        cands.append(e)
    cands.sort(key=lambda e: (-e["value_named"]["share_top_n"], -e["value_named"]["share_top_k"],
                              -(e["value_named"].get("median_similarity") or 0)))
    by_id = {c["statsbomb_player_id"]: c for c in cands}
    rec = [{"player_id": int(p["player_id"]), "in_core": p["in_core"],
            "name": by_id[int(p["player_id"])].get("name")} for p in picks]

    scen = []
    for s in sens_cfg["scenarios"]:
        f, res = named[s["id"]], run_out["results"][s["id"]]
        top = f["value_rank"].dropna().sort_values(kind="mergesort").index[:n]
        stop = f.sort_values("similarity_rank", kind="mergesort").index[:n]
        scen.append({"id": s["id"], "label": s["label"], "kind": s["kind"], "changes": s["changes"],
                     "config_sha256": run_out["fingerprints"][s["id"]],
                     "pool": res["counts"]["pool"], "eligible": res["counts"]["eligible"],
                     "value_top_n": [int(i) for i in top], "similarity_top_n": [int(i) for i in stop]})
    base_top = set(scen[0]["value_top_n"])
    for s in scen:
        s["overlap_with_base"] = len(base_top & set(s["value_top_n"]))
    W = pd.DataFrame(run_out["draw_weights"])
    return {
        "target": run_r4.entry(t, target, keys, groups),
        "scenarios": scen,
        "named": {"scenarios": len(named), "similarity_view": len(sim_ids)},
        "similarity_view_scenarios": sim_ids,
        "draws": {"draws": len(run_out["draws"]), **sens_cfg["random_weights"],
                  "weights": {g: {"mean": _num(W[g].mean()), "sd": _num(W[g].std(ddof=0)),
                                  "min": _num(W[g].min()), "max": _num(W[g].max())} for g in W.columns}},
        "robust_core": [int(p) for p in core],
        "recommendation": rec,
        "candidates": cands,
    }
