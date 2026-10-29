"""R3 SQL (club map check, squads, plausibility, valuations, age) on the hand-made tables in r3_data.py."""
import copy
from datetime import date

import pytest

from recruit import config, load, market_values
from tests import r3_data

CFG = config.load("matching")


def _con():
    con = load.connect(":memory:", "1GB", 1)
    r3_data.build(con)
    return con


@pytest.fixture(scope="module")
def con():
    con = _con()
    market_values.build(con, r3_data.SCOPE, r3_data.CLUB_MAP, r3_data.OVERRIDES, CFG)
    return con


def row(con, sb_id):
    rel = con.execute("SELECT * FROM r3_player_values WHERE player_id = ?", [sb_id])
    cols = [d[0] for d in rel.description]
    return dict(zip(cols, rel.fetchone()))


# --- club map --------------------------------------------------------------------------------------

def test_club_map_check_passes_and_reports_date_overlap():
    rows = market_values.check_club_map(_con(), r3_data.SCOPE, r3_data.CLUB_MAP, CFG)
    assert {r["statsbomb_team_id"]: (r["sb_matches"], r["dates_covered"]) for r in rows} == \
        {1: (5, 5), 2: (4, 4), 3: (5, 5)}   # Beta's only player plays 4


@pytest.mark.parametrize("change, message", [
    (lambda m: m["clubs"].pop(), "not in config/club_map.yaml"),                       # team missing
    (lambda m: m["clubs"].append(dict(m["clubs"][0])), "more than once"),             # team twice
    (lambda m: m["clubs"][1].update(transfermarkt_club_id=101), "more than once"),    # club twice
    (lambda m: m["clubs"][0].update(transfermarkt_club_id=999), "date overlap"),      # wrong club
])
def test_club_map_check_stops_on_problems(change, message):
    club_map = copy.deepcopy(r3_data.CLUB_MAP)
    change(club_map)
    with pytest.raises(ValueError, match=message):
        market_values.check_club_map(_con(), r3_data.SCOPE, club_map, CFG)


# --- squads ----------------------------------------------------------------------------------------

def test_squads_use_the_season_window(con):
    gamma = {r[0] for r in con.execute("SELECT transfermarkt_player_id FROM r3_squads WHERE statsbomb_team_id = 3").fetchall()}
    assert gamma == {1008, 1009}          # 1011's Gamma game is from 2014, outside the window
    apps = con.execute("SELECT league_apps, all_apps FROM r3_squads WHERE statsbomb_team_id = 1 "
                       "AND transfermarkt_player_id = 1001").fetchone()
    assert apps == (5, 6)                 # five league games and one cup game


# --- joined table ----------------------------------------------------------------------------------

def test_every_statsbomb_player_has_one_row(con):
    assert con.execute("SELECT count(*), count(DISTINCT player_id) FROM r3_player_values").fetchone() == (10, 10)


def test_valuation_after_the_date_is_ignored(con):
    r = row(con, 11)
    assert r["transfermarkt_player_id"] == 1001
    assert r["market_value_eur"] == 20_000_000          # not the 30m from 2016-08-01
    assert r["valuation_date"] == date(2016, 6, 1)
    assert r["valuation_gap_days"] == 30
    assert r["valuation_stale"] is False
    assert r["age"] == 25 and r["age_years"] == pytest.approx(9226 / 365.25)   # 1991-03-29 to 2016-07-01


def test_old_valuation_is_flagged_not_dropped(con):
    r = row(con, 12)
    assert r["market_value_eur"] == 8_000_000 and r["valuation_gap_days"] == 547 and r["valuation_stale"] is True


def test_only_later_valuation_means_no_price(con):
    r = row(con, 13)
    assert r["transfermarkt_player_id"] == 1003
    assert r["market_value_eur"] is None and r["valuation_date"] is None and r["valuation_stale"] is None


def test_unmatched_player_keeps_profile_row_without_price(con):
    r = row(con, 16)
    assert r["transfermarkt_player_id"] is None and r["status"] == "ambiguous" and r["market_value_eur"] is None


def test_mid_season_mover_is_matched_at_both_clubs(con):
    rows = con.execute("SELECT statsbomb_team_id, sb_matches, tm_league_apps, gap_flag FROM r3_plausibility "
                       "WHERE player_id = 18 ORDER BY statsbomb_team_id").fetchall()
    assert rows == [(2, 4, 4, False), (3, 3, 3, False)]
    r = row(con, 18)
    assert r["transfermarkt_player_id"] == 1008 and r["clubs_with_appearances"] == 2 and r["n_teams"] == 2


def test_plausibility_flags_a_large_gap(con):
    assert con.execute("SELECT sb_matches, tm_league_apps, gap_flag FROM r3_plausibility WHERE player_id = 12"
                       ).fetchall() == [(5, 1, True)]
    assert row(con, 12)["plausibility_flag"] is True
    assert row(con, 11)["plausibility_flag"] is False


def test_outside_squad_override_must_exist_in_tm_players():
    overrides = {"overrides": [{"statsbomb_player_id": 19, "transfermarkt_player_id": 5555, "outside_squad": True,
                                "reason": "r", "evidence": "e"}]}
    with pytest.raises(ValueError, match="not in tm_players"):
        market_values.build(_con(), r3_data.SCOPE, r3_data.CLUB_MAP, overrides, CFG)
