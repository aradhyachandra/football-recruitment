"""R3: match StatsBomb players to transfermarkt-datasets players by name, inside club squads.

There is no shared id. A StatsBomb player is compared only with the Transfermarkt players who played
for his club(s) in the season (the squads come from sql/r3_squads.sql). Each candidate gets a score
and a method label:

    exact_name / exact_nickname  same normalised name                                  score 1.0
    token_subset                 every word of one name appears in the other           0.95 (one word: 0.88)
    token_prefix                 same other words, first names share 3+ letters        0.87
    fuzzy                        close spelling (difflib ratio, whole name or by word)  the ratio
    override                     config/player_overrides.yaml                          no score

The best candidate is taken only if it clears min_score and no other candidate is within the
ambiguity margin; otherwise country breaks the tie ("+country" is added to the method) or the player
is left unmatched. Rules and numbers come from config/matching.yaml.
"""
from __future__ import annotations

import os
import unicodedata
from difflib import SequenceMatcher


def normalise(text: str | None, cfg: dict) -> str:
    """Lower case, no apostrophes, hyphens and dots as spaces, no accents, single spaces."""
    if not text:
        return ""
    rules = cfg["normalise"]
    s = text.lower()
    for ch in rules["apostrophes"]:
        s = s.replace(ch, "")
    for ch in rules["separators"]:
        s = s.replace(ch, " ")
    for ch, repl in rules["transliterate"].items():
        s = s.replace(ch, repl)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return " ".join(s.split())


def country(text: str | None, cfg: dict) -> str:
    s = normalise(text, cfg)
    return cfg["country_aliases"].get(s, s)


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def score(sb: dict, tm: dict, cfg: dict) -> tuple[float, str | None]:
    """Best (score, method) for one StatsBomb player (names, nicknames) against one Transfermarkt player."""
    sc = cfg["scores"]
    names = {normalise(n, cfg) for n in sb["names"]} - {""}
    nicks = {normalise(n, cfg) for n in sb["nicknames"]} - {""}
    tm_forms = {normalise(tm["name"], cfg),
                normalise(" ".join(p for p in (tm.get("first_name"), tm.get("last_name")) if p), cfg)} - {""}
    if names & tm_forms:
        return sc["exact"], "exact_name"
    if nicks & tm_forms:
        return sc["exact"], "exact_nickname"

    best = (0.0, None)
    sb_words = {w for form in names | nicks for w in form.split()}
    tm_words = set(normalise(tm["name"], cfg).split())
    subsets = []
    if tm_words and tm_words <= sb_words:
        subsets.append(len(tm_words))
    subsets += [len(form.split()) for form in names | nicks if set(form.split()) <= tm_words]
    if subsets:
        best = (sc["token_subset_multi"] if max(subsets) > 1 else sc["token_subset_single"], "token_subset")
    else:
        first, *rest = normalise(tm["name"], cfg).split() or [""]
        if rest and set(rest) <= sb_words and any(
                len(os.path.commonprefix([first, w])) >= sc["token_prefix_min_letters"] for w in sb_words - set(rest)):
            best = (sc["token_prefix"], "token_prefix")

    fuzzy = max((_ratio(a, b) for a in names | nicks for b in tm_forms), default=0.0)
    if len(tm_words) > 1 and sb_words and not subsets:   # with a subset every word scores 1.0 anyway
        fuzzy = max(fuzzy, sum(max(_ratio(w, s) for s in sb_words) for w in tm_words) / len(tm_words))
    if fuzzy > best[0]:
        best = (fuzzy, "fuzzy")
    return best


def _check_overrides(overrides: list[dict]) -> dict[int, dict]:
    out = {}
    for o in overrides:
        if not o.get("reason") or not o.get("evidence"):
            raise ValueError(f"override for StatsBomb player {o['statsbomb_player_id']} needs a reason and evidence")
        if o["statsbomb_player_id"] in out:
            raise ValueError(f"StatsBomb player {o['statsbomb_player_id']} has two overrides")
        out[o["statsbomb_player_id"]] = o
    return out


def _row(player_id, tm_id=None, method=None, score_=None, status="matched", scored=(), n=0) -> dict:
    best = scored[0] if scored else None
    return {"statsbomb_player_id": player_id, "transfermarkt_player_id": tm_id, "method": method,
            "score": score_, "status": status, "n_candidates": n,
            "best_candidate_id": best[2]["player_id"] if best else None,
            "best_candidate_name": best[2]["name"] if best else None,
            "best_score": best[0] if best else None,
            "second_score": scored[1][0] if len(scored) > 1 else None}


def match_one(player: dict, candidates: list[dict], cfg: dict) -> dict:
    scored = sorted(((*score(player, c, cfg), c) for c in candidates),
                    key=lambda t: (-t[0], t[2]["player_id"]))
    pid, n = player["player_id"], len(candidates)
    if not scored:
        return _row(pid, status="no_candidates")
    top = scored[0][0]
    if top < cfg["min_score"]:
        return _row(pid, status="low_score", scored=scored, n=n)
    close = [t for t in scored if t[0] >= top - cfg["ambiguity_margin"]]
    if len(close) == 1:
        return _row(pid, close[0][2]["player_id"], close[0][1], top, scored=scored, n=n)
    sb_countries = {country(c, cfg) for c in player["countries"]} - {""}
    same = [t for t in close if sb_countries & ({country(c, cfg) for c in t[2]["countries"]} - {""})]
    if len(same) == 1 and same[0][0] >= cfg["min_score"]:
        s, method, cand = same[0]
        return _row(pid, cand["player_id"], f"{method}+country", s, scored=scored, n=n)
    return _row(pid, status="ambiguous", scored=scored, n=n)


def match_players(players: list[dict], squads: dict[int, list[dict]], overrides: list[dict], cfg: dict) -> list[dict]:
    """players: player_id, names, nicknames, countries, team_ids. squads: StatsBomb team id -> Transfermarkt
    candidates (player_id, name, first_name, last_name, countries). One row per StatsBomb player."""
    by_id = _check_overrides(overrides)
    rows = []
    for p in players:
        candidates = list({c["player_id"]: c for t in p["team_ids"] for c in squads.get(t, [])}.values())
        o = by_id.get(p["player_id"])
        if o is None:
            rows.append(match_one(p, candidates, cfg))
        elif o["transfermarkt_player_id"] is None:
            rows.append(_row(p["player_id"], status="override_unmatched", n=len(candidates)))
        elif not o.get("outside_squad") and o["transfermarkt_player_id"] not in {c["player_id"] for c in candidates}:
            raise ValueError(f"override: Transfermarkt player {o['transfermarkt_player_id']} is not in the squad "
                             f"of StatsBomb player {p['player_id']}'s club(s)")
        else:
            rows.append(_row(p["player_id"], o["transfermarkt_player_id"], "override", None, n=len(candidates)))

    # one Transfermarkt player for one StatsBomb player: an override or a strictly better score wins
    claims: dict[int, list[dict]] = {}
    for r in rows:
        if r["transfermarkt_player_id"] is not None:
            claims.setdefault(r["transfermarkt_player_id"], []).append(r)
    for group in claims.values():
        if len(group) < 2:
            continue
        rank = sorted(group, key=lambda r: -(2.0 if r["method"] == "override" else r["score"]))
        first = 2.0 if rank[0]["method"] == "override" else rank[0]["score"]
        second = 2.0 if rank[1]["method"] == "override" else rank[1]["score"]
        losers = rank[1:] if first > second else rank
        for r in losers:
            if r["method"] == "override" and first == second:
                raise ValueError(f"two overrides give Transfermarkt player {r['transfermarkt_player_id']}")
            r.update(transfermarkt_player_id=None, method=None, score=None, status="ambiguous_shared")
    return rows
