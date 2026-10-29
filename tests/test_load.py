"""Loading flattened parquet and transfermarkt CSVs into DuckDB with explicit column types."""
import pytest

from recruit import flatten, load


@pytest.fixture
def con(sb_raw, tm_raw, fields, tmp_path):
    flatten.flatten_all(sb_raw, tmp_path / "processed", 27, [2, 7], fields)
    c = load.connect(":memory:", "1GB", 1)
    load.load_statsbomb(c, tmp_path / "processed", fields)
    load.load_transfermarkt(c, {t: tm_raw / f"{t}.csv" for t in load.TM_TABLES})
    yield c
    c.close()


def types(con, table):
    return {r[0]: r[1] for r in con.execute(f"DESCRIBE {table}").fetchall()}


def test_row_counts(con):
    counts = load.row_counts(con)
    assert counts == {"sb_matches": 2, "sb_events": 11, "sb_lineup_players": 7,
                      "sb_lineup_positions": 7, "tm_players": 5, "tm_player_valuations": 7,
                      "tm_clubs": 5, "tm_appearances": 6}


def test_statsbomb_types_come_from_the_field_config(con):
    ev = types(con, "sb_events")
    assert ev["match_id"] == "BIGINT" and ev["competition_id"] == "INTEGER"
    assert ev["shot_xg"] == "DOUBLE" and ev["under_pressure"] == "BOOLEAN"
    assert ev["event_id"] == "VARCHAR"
    assert types(con, "sb_matches")["match_date"] == "DATE"
    assert con.execute("SELECT match_date FROM sb_matches WHERE match_id = 101").fetchone()[0].isoformat() \
        == "2015-08-08"


def test_transfermarkt_types_and_dropped_columns(con):
    pl = types(con, "tm_players")
    assert pl["player_id"] == "BIGINT" and pl["date_of_birth"] == "DATE"
    assert pl["height_in_cm"] == "INTEGER"
    # today's market value would be hindsight; it is not loaded
    assert "market_value_in_eur" not in pl and "image_url" not in pl
    val = types(con, "tm_player_valuations")
    assert val["date"] == "DATE" and val["market_value_in_eur"] == "BIGINT"
    assert types(con, "tm_appearances")["minutes_played"] == "INTEGER"
    assert con.execute("SELECT height_in_cm, foot FROM tm_players WHERE player_id = 1002").fetchone() \
        == (None, None)


def test_bad_value_stops_the_load(tm_raw, tmp_path):
    bad = tmp_path / "player_valuations.csv"
    bad.write_text(tm_raw.joinpath("player_valuations.csv").read_text().replace("2016-02-01", "not-a-date"))
    paths = {t: tm_raw / f"{t}.csv" for t in load.TM_TABLES} | {"player_valuations": bad}
    c = load.connect(":memory:", "1GB", 1)
    with pytest.raises(Exception, match="not-a-date"):
        load.load_transfermarkt(c, paths)
