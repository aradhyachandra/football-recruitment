"""R1 audit and gates, checked on the hand-made fixtures (expected values worked out by hand)."""
import pytest

from recruit import audit, config, flatten, load

SCOPE = {
    "competitions": [{"competition_id": 2, "name": "Premier League", "transfermarkt_id": "GB1"},
                     {"competition_id": 7, "name": "Ligue 1", "transfermarkt_id": "FR1"}],
    "valuation_date": "2016-07-01",
    "season_window": {"start": "2015-07-01", "end": "2016-06-30"},
    "departing_player": {"statsbomb_name": "N'Golo Kanté"},
    "departing_player_ids": {"transfermarkt_player_id": 225083},
}


@pytest.fixture
def cfg():
    return config.load("audit")


@pytest.fixture
def con(sb_raw, tm_raw, fields, tmp_path):
    flatten.flatten_all(sb_raw, tmp_path / "processed", 27, [2, 7], fields)
    c = load.connect(":memory:", "1GB", 1)
    load.load_statsbomb(c, tmp_path / "processed", fields)
    load.load_transfermarkt(c, {t: tm_raw / f"{t}.csv" for t in load.TM_TABLES})
    yield c
    c.close()


def test_league_summary(con):
    rows = {r["competition_id"]: r for r in audit.league_summary(con, SCOPE)}
    assert rows[2] == {"competition_id": 2, "league": "Premier League", "matches": 1, "events": 9,
                       "teams": 2, "squad_players": 5, "players_who_played": 4}
    assert rows[7]["events"] == 2 and rows[7]["players_who_played"] == 2


def test_event_type_counts(con):
    rows = audit.event_type_counts(con, SCOPE)
    pl = {r["type_name"]: r for r in rows}
    assert pl["Pressure"]["Premier League"] == 1 and pl["Pressure"]["Ligue 1"] == 1
    assert pl["Pass"]["total"] == 2 and pl["Shot"]["Ligue 1"] == 0
    assert rows[0]["total"] >= rows[-1]["total"]  # most frequent first


def test_valuation_gate(con, cfg):
    g = audit.valuation_gate(con, SCOPE, cfg | {"valuation_gate": cfg["valuation_gate"] | {"min_share_before": 0.3}})
    # league players in the season window: Kante, Alpha (GB1), Beta (FR1); Gamma is Bundesliga,
    # Delta only played in 2014
    assert g["players"] == 3
    assert g["with_valuation_before"] == 1 and g["share_before"] == pytest.approx(1 / 3)
    # no counts built from valuations after the date (no hindsight in public results)
    assert not any("either_side" in k for k in g) and not any("either_side" in k for k in g["by_league"][0])
    by = {r["league"]: r for r in g["by_league"]}
    assert (by["GB1"]["players"], by["GB1"]["with_valuation_before"]) == (2, 1)
    assert (by["FR1"]["players"], by["FR1"]["with_valuation_before"]) == (1, 0)
    d = g["departing_player"]
    assert d["latest_before"] == {"date": "2016-02-01", "market_value_eur": 18000000, "days_before": 151}
    # the 2016-07-15 Chelsea valuation is after the date and must not be listed
    assert [h["date"] for h in d["history"]] == ["2015-07-01", "2016-02-01"]
    assert {h["club"] for h in d["history"]} == {"Leicester City"}
    assert g["passed"] is True
    strict = audit.valuation_gate(con, SCOPE, cfg)  # default 80% line
    assert strict["passed"] is False


def test_valuation_gate_fails_without_departing_player_value(con, cfg):
    scope = SCOPE | {"departing_player_ids": {"transfermarkt_player_id": 1002}}
    loose = cfg | {"valuation_gate": cfg["valuation_gate"] | {"min_share_before": 0.0}}
    g = audit.valuation_gate(con, scope, loose)
    assert g["departing_player"]["latest_before"] is None and g["passed"] is False


def test_pressure_gate(con, cfg):
    g = audit.pressure_gate(con, SCOPE, cfg)
    by = {r["league"]: r for r in g["by_league"]}
    assert by["Premier League"] == {"league": "Premier League", "pressure_events": 1, "matches": 1,
                                    "matches_with_pressure": 1}
    assert g["passed"] is True


def test_pressure_gate_fails_when_a_league_has_none(con, cfg):
    con.execute("DELETE FROM sb_events WHERE competition_id = 7 AND type_name = 'Pressure'")
    g = audit.pressure_gate(con, SCOPE, cfg)
    assert g["passed"] is False


def test_lineup_gate(con, cfg):
    g = audit.lineup_gate(con, SCOPE, cfg)
    assert g["position_rows"] == 7 and g["with_from_time"] == 7 and g["share_from_time"] == 1.0
    assert g["matches"] == 2 and g["matches_with_both_teams"] == 2
    assert g["open_ended_by_end_reason"] == [{"end_reason": "Final Whistle", "rows": 5}]
    assert g["passed"] is True
    con.execute("UPDATE sb_lineup_positions SET from_time = NULL WHERE player_id = 9")
    assert audit.lineup_gate(con, SCOPE, cfg)["passed"] is False


def test_resource_gate(cfg):
    sizes = {"statsbomb_raw_bytes": 10, "statsbomb_raw_files": 3, "transfermarkt_raw_bytes": 5,
             "transfermarkt_raw_files": 4, "parquet_bytes": 2, "duckdb_bytes": 1}
    g = audit.resource_gate({"peak_rss_bytes": 500 * 2**20, "seconds": 1.0}, sizes, cfg)
    assert g["peak_rss_gb"] == pytest.approx(500 / 1024) and g["passed"] is True
    assert g["statsbomb_raw_bytes"] == 10
    assert audit.resource_gate({"peak_rss_bytes": 3 * 2**30, "seconds": 1.0}, sizes, cfg)["passed"] is False


def test_departing_player_in_statsbomb(con):
    d = audit.departing_player_statsbomb(con, SCOPE)
    assert d == [{"player_id": 7, "player_name": "N'Golo Kanté", "team_name": "Leicester City",
                  "matches_listed": 1, "matches_played": 1}]
