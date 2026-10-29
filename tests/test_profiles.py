"""R2 SQL on the hand-made tables in tests/r2_data.py. Expected numbers are worked out by hand there."""
import copy

import pytest

from recruit import config, load, profiles
from tests import r2_data

SCOPE = {"competitions": [{"competition_id": 2, "name": "Premier League"},
                          {"competition_id": 7, "name": "Ligue 1"}],
         "departing_player_ids": {"statsbomb_player_id": 2}}


def _configs():
    cfg = profiles.load_configs()
    # small thresholds so the hand-made players form pools
    cfg["profiles"]["minutes"].update(threshold=90, sensitivity_thresholds=[60, 90, 120])
    # the glitched event in r2_data steps back 43.5 s in a short hand-made half; real halves need 60 s
    cfg["profiles"]["event_timestamps"]["max_backward_seconds"] = 30
    return cfg


@pytest.fixture(scope="module")
def con():
    con = load.connect(":memory:", "1GB", 1)
    r2_data.build(con)
    profiles.build(con, SCOPE, _configs())
    return con


def rows(con, sql, params=None):
    rel = con.execute(sql, params or [])
    cols = [d[0] for d in rel.description]
    return [dict(zip(cols, r)) for r in rel.fetchall()]


def minutes(con, match_id, player_id):
    return con.execute("SELECT sum(minutes) FROM r2_stints WHERE match_id = ? AND player_id = ?",
                       [match_id, player_id]).fetchone()[0]


# --- minutes -----------------------------------------------------------------------------------

def test_period_lengths_come_from_half_end_events(con):
    got = rows(con, "SELECT period, length_s, offset_s, match_length_s FROM r2_period_lengths "
                    "WHERE match_id = 1 ORDER BY period")
    assert got == [{"period": 1, "length_s": 2730.0, "offset_s": 0.0, "match_length_s": 5610.0},
                   {"period": 2, "length_s": 2880.0, "offset_s": 2730.0, "match_length_s": 5610.0}]


@pytest.mark.parametrize("player_id, expected", [
    (1, 93.5),   # full match: open-ended spell runs to the final whistle, added time included
    (3, 60.5),   # substituted at 60:00 in period 2: 2730 + (3600 - 2700) s
    (4, 33.0),   # came on at 60:00
    (5, 30.0),   # red card at 30:00
    (6, 45.5),   # half-time substitution ("to" 45:00 in period 2) gets all first-half added time
    (7, 48.0),   # came on at half-time
    (2, 93.5),   # position change at 70:00: two spells, 70.5 + 23.0
    (8, 90.5),   # temporary "Player Off" 20:00-23:00 does not count
    (9, 45.5),   # clock 46:10 in a 45:30 first half is kept inside the period
    (12, 48.0),
])
def test_minutes_from_lineup_spells(con, player_id, expected):
    assert minutes(con, 1, player_id) == pytest.approx(expected)


def test_minutes_by_position_change(con):
    got = rows(con, "SELECT position_id, role, minutes FROM r2_stints WHERE match_id = 1 AND player_id = 2 "
                    "ORDER BY start_s")
    assert [(r["position_id"], r["role"]) for r in got] == [(13, "Central midfielder"),
                                                            (10, "Central midfielder")]
    assert [r["minutes"] for r in got] == pytest.approx([70.5, 23.0])


def test_team_minutes_check(con):
    tm = profiles.team_minutes_check(con, _configs())
    # match 1: team 20 has 11 x 93.5 exactly; team 10 has 962 of 1028.5 (red card, player off);
    # match 2 has one player per team, far below (no red card or player off): unexplained
    assert tm["team_matches"] == 4
    assert tm["within_tolerance"] == 1
    assert tm["below_with_red_card"] == 1
    assert tm["below_unexplained"] == 2
    assert tm["max_ratio"] == pytest.approx(1.0)
    team10 = con.execute("SELECT sum(minutes) FROM r2_stints WHERE match_id = 1 AND team_id = 10").fetchone()[0]
    assert team10 == pytest.approx(962.0)


# --- possession ----------------------------------------------------------------------------------

def test_possession_in_play_share_and_pass_share(con):
    got = {r["team_id"]: r for r in rows(con, "SELECT * FROM r2_team_possession WHERE match_id = 1")}
    assert got[10]["in_play_seconds"] == pytest.approx(17.0)
    assert got[20]["in_play_seconds"] == pytest.approx(8.5)
    assert got[10]["in_play_share"] == pytest.approx(2 / 3)
    assert got[10]["pass_share"] == pytest.approx(4 / 7)
    m2 = {r["team_id"]: r["in_play_share"] for r in rows(con, "SELECT * FROM r2_team_possession WHERE match_id = 2")}
    assert m2[30] == pytest.approx(0.75)


def test_possession_check_summary(con):
    chk = profiles.possession_check(con)
    # |2/3 - 4/7| for both teams of match 1; |0.75 - 0.5| for both teams of match 2
    assert chk["team_matches"] == 4
    assert chk["max_abs_diff"] == pytest.approx(0.25)
    assert chk["mean_abs_diff"] == pytest.approx((2 * (2 / 3 - 4 / 7) + 2 * 0.25) / 4)


# --- event definitions ----------------------------------------------------------------------------

EXPECTED_MATCH1_PLAYER2 = {
    "tackles_won": 1,              # Won counts, Lost In Play does not
    "interceptions": 1,            # counted whatever the outcome (Lost Out here)
    "ball_recoveries": 1,          # the failed recovery is left out
    "pressures": 2,
    "pressure_regains": 1,         # 3.5 s to A's next sequence counts, 9 s does not
    "blocks": 1,
    "fouls_committed": 1,
    "passes_completed": 3,         # open-play pass, key pass, throw-in
    "passes_attempted": 3,         # injury clearance is not an attempt
    "progressive_passes": 2,       # 60 -> 30 from goal, 22.4 -> 10; the throw-in is a restart
    "passes_into_final_third": 1,  # x 60 -> 90; the key pass starts beyond x = 80
    "progressive_carries": 1,      # 30 -> 20 from goal
    "successful_dribbles": 1,
    "shots": 0,
    "np_xg": 0,
    "key_passes": 1,
}


def test_event_definitions_player_match(con):
    got = {r["metric"]: r["raw"] for r in rows(
        con, "SELECT metric, raw FROM r2_player_match WHERE match_id = 1 AND player_id = 2")}
    assert got == pytest.approx(EXPECTED_MATCH1_PLAYER2)


def test_penalties_left_out_of_shots_and_xg(con):
    got = {r["metric"]: r["raw"] for r in rows(
        con, "SELECT metric, raw FROM r2_player_match WHERE match_id = 1 AND player_id = 3")}
    assert got["shots"] == 1
    assert got["np_xg"] == pytest.approx(0.3)


def test_possession_adjustment_per_match(con):
    got = rows(con, "SELECT match_id, raw, opponent_share, adjusted FROM r2_player_match "
                    "WHERE player_id = 2 AND metric = 'tackles_won' ORDER BY match_id")
    # match 1: opponent had 1/3 -> x1.5; match 2: opponent had 0.25 -> x2
    assert [r["adjusted"] for r in got] == pytest.approx([1.5, 2.0])
    passes = rows(con, "SELECT adjusted FROM r2_player_match WHERE player_id = 2 AND metric = 'passes_completed'")
    assert all(r["adjusted"] is None for r in passes)  # only defensive metrics are adjusted


# --- player season ---------------------------------------------------------------------------------

def test_mover_gets_one_row_with_teams_kept(con):
    p = rows(con, "SELECT * FROM r2_players WHERE player_id = 2")[0]
    assert p["minutes"] == pytest.approx(183.5)
    assert p["moved_mid_season"] is True and p["n_leagues"] == 2
    assert [(t["team_id"], t["minutes"]) for t in p["teams"]] == [(10, 93.5), (30, 90.0)]
    assert p["main_competition_id"] == 2
    # 93.5 min central midfield (match 1) v 90 min left midfield (match 2)
    assert p["role"] == "Central midfielder"
    assert p["role_share"] == pytest.approx(93.5 / 183.5)


def test_per90_raw_and_adjusted(con):
    got = {r["metric"]: r for r in rows(con, "SELECT * FROM r2_player_season WHERE player_id = 2")}
    assert got["tackles_won"]["total_raw"] == 2
    assert got["tackles_won"]["value"] == pytest.approx(2 * 90 / 183.5)
    assert got["tackles_won"]["value_padj"] == pytest.approx(3.5 * 90 / 183.5)
    assert got["passes_completed"]["value"] == pytest.approx(4 * 90 / 183.5)
    assert got["passes_completed"]["value_padj"] is None
    assert got["pass_completion"]["kind"] == "ratio"
    assert got["pass_completion"]["value"] == pytest.approx(1.0)
    assert "passes_attempted" not in got  # helper total, not part of the profile


def test_pass_completion_counts_incomplete_passes(con):
    v = con.execute("SELECT value FROM r2_player_season WHERE player_id = 21 AND metric = 'pass_completion'")
    assert v.fetchone()[0] == pytest.approx(0.5)


def test_pool_sizes_by_threshold(con):
    pools = profiles.pool_sizes(con, SCOPE, _configs())
    cm = {(r["threshold"], r["league"]): r["players"] for r in pools if r["role"] == "Central midfielder"}
    # >= 90 min: players 2 (183.5), 8 (90.5), 13 (93.5), 21, 27 (93.5) in the PL; 41 (90.0) in Ligue 1
    assert cm[(90, "Premier League")] == 5
    assert cm[(90, "Ligue 1")] == 1
    assert cm.get((120, "Premier League")) == 1


def test_movers_counted(con):
    chk = profiles.checks(con, _configs())
    assert chk["movers"] == 1 and chk["movers_between_leagues"] == 1
    assert chk["stints_without_role"] == 0
    assert chk["events_without_stint"] == 0
    assert chk["bad_timestamp_events"] == 1


def test_departing_profile_percentile_ranks(con):
    prof = {r["metric"]: r for r in profiles.departing_profile(con, SCOPE, _configs())}
    # pool: six central midfielders >= 90 min; only player 2 has any tackles
    assert prof["tackles_won"]["pool_size"] == 6
    assert prof["tackles_won"]["pct_rank"] == pytest.approx(1.0)
    assert prof["tackles_won"]["pct_rank_padj"] == pytest.approx(1.0)
    assert prof["shots"]["pct_rank"] == 0.0           # all tied at zero
    assert prof["pass_completion"]["pct_rank_padj"] is None


def test_distributions_are_percentiles_not_players(con):
    dist = profiles.distributions(con, _configs())
    row = next(d for d in dist if d["role"] == "Central midfielder" and d["metric"] == "tackles_won")
    assert row["players"] == 6
    # values sorted: five zeros and 2*90/183.5; the 90th percentile interpolates half-way to it
    assert row["value"]["p90"] == pytest.approx(0.5 * 2 * 90 / 183.5)
    assert row["value"]["p50"] == 0
    assert set(row) == {"role", "metric", "kind", "players", "value", "value_padj"}


def test_metric_config_is_validated():
    cfg = _configs()
    bad = copy.deepcopy(cfg)
    bad["metrics"]["metrics"][0]["value"] = "minute"
    with pytest.raises(ValueError):
        profiles.metric_def_rows(bad["metrics"])
    bad = copy.deepcopy(cfg)
    bad["metrics"]["metrics"][0]["flags_true"] = ["not_a_flag"]
    with pytest.raises(ValueError):
        profiles.metric_def_rows(bad["metrics"])


def test_every_statsbomb_position_has_a_role():
    roles = config.load("roles")["roles"]
    ids = [p for r in roles for p in r["positions"]]
    assert sorted(ids) == list(range(1, 26)) and len(ids) == len(set(ids))


def test_summary_and_doc_render_from_hand_made_data(con):
    import json

    from recruit import run_r2

    scope = SCOPE | {"season": {"season_id": 27}, "departing_player": {"statsbomb_name": "Player Two"}}
    s = run_r2.build_summary(con, scope, _configs())
    json.dumps(s, default=str)  # the saved summary must be plain JSON
    d = s["departing_player"]
    assert d["role"] == "Central midfielder" and d["minutes"] == pytest.approx(183.5)
    assert [t["minutes"] for t in d["teams"]] == [93.5, 90.0]
    # possession share weighted by his minutes: (2/3 * 93.5 + 0.75 * 90) / 183.5
    assert d["avg_team_share"] == pytest.approx((2 / 3 * 93.5 + 0.75 * 90) / 183.5)
    doc = run_r2.render(s, run_r2.TEMPLATE.read_text(encoding="utf-8"), scope)
    assert "{{" not in doc
    assert "| Tackles won |" in doc
    # results/ must not carry other players' rows: only percentiles by role and the case player
    assert all(set(r) <= {"role", "metric", "kind", "players", "value", "value_padj", "label"}
               for r in s["distributions"])
