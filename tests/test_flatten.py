"""Flattening StatsBomb JSON to typed columns, checked against hand-made fixtures."""
import json

import pyarrow.parquet as pq
import pytest

from recruit import flatten


def test_extract_paths_alternatives_lists_and_defaults():
    spec = [
        {"name": "a", "path": "x.y", "type": "int64"},
        {"name": "b", "path": ["p.q", "r.q"], "type": "string"},
        {"name": "c", "path": "loc.1", "type": "float64"},
        {"name": "d", "path": "flag", "type": "bool", "default": False},
        {"name": "e", "path": "missing.deep", "type": "string"},
    ]
    rec = {"x": {"y": 5}, "r": {"q": "second"}, "loc": [1.0, 2.5]}
    assert flatten.extract(rec, spec) == {"a": 5, "b": "second", "c": 2.5, "d": False, "e": None}


def test_events_one_row_per_event_with_selected_fields(sb_raw, fields):
    events = json.loads((sb_raw / "events/101.json").read_text())
    t = flatten.events_table(events, match_id=101, competition_id=2, spec=fields["events"])
    assert t.num_rows == 9
    rows = {r["event_id"]: r for r in t.to_pylist()}
    assert rows["e1"]["player_id"] is None and rows["e1"]["location_x"] is None
    p = rows["e2"]
    assert (p["match_id"], p["competition_id"], p["type_name"]) == (101, 2, "Pass")
    assert (p["location_x"], p["end_x"], p["end_y"]) == (60.0, 90.0, 40.0)
    assert p["outcome_name"] is None  # complete pass has no outcome in StatsBomb
    assert p["pass_shot_assist"] is True and p["pass_cross"] is False
    assert p["pass_recipient_id"] == 8 and p["pass_height"] == "Ground Pass"
    s = rows["e3"]
    assert (s["shot_xg"], s["outcome_name"], s["subtype_name"]) == (0.25, "Goal", "Open Play")
    assert s["shot_key_pass_id"] == "e2" and s["under_pressure"] is True and s["end_x"] == 120.0
    assert rows["e4"]["counterpress"] is True and rows["e4"]["under_pressure"] is False
    assert (rows["e5"]["subtype_name"], rows["e5"]["outcome_name"]) == ("Tackle", "Won")
    assert rows["e6"]["end_x"] == 65.5
    assert rows["e7"]["ball_recovery_failure"] is True
    assert rows["e8"]["card_name"] == "Yellow Card"
    assert rows["e9"]["substitution_replacement_id"] == 10 and rows["e9"]["outcome_name"] == "Tactical"
    # dropped fields never reach the table
    assert "freeze_frame" not in t.column_names and "tactics" not in t.column_names


def test_events_column_types(sb_raw, fields):
    events = json.loads((sb_raw / "events/101.json").read_text())
    t = flatten.events_table(events, 101, 2, fields["events"])
    types = {f.name: str(f.type) for f in t.schema}
    assert types["match_id"] == "int64" and types["competition_id"] == "int32"
    assert types["player_id"] == "int64" and types["minute"] == "int32"
    assert types["shot_xg"] == "double" and types["under_pressure"] == "bool"
    assert types["event_id"] == "string"


def test_lineups_players_and_position_stints(sb_raw, fields):
    lineups = json.loads((sb_raw / "lineups/101.json").read_text())
    players, positions = flatten.lineup_tables(lineups, 101, 2, fields["lineup_players"],
                                               fields["lineup_positions"])
    assert players.num_rows == 5  # unused substitute Hamer kept as a player row
    assert positions.num_rows == 5  # Kante 1, Vardy 2, Ulloa 1, Cattermole 1, Hamer 0
    vardy = [r for r in positions.to_pylist() if r["player_id"] == 9]
    assert [(r["from_time"], r["to_time"], r["position_id"]) for r in vardy] == [
        ("00:00", "60:00", 23), ("60:00", "75:00", 24)]
    assert vardy[0]["team_id"] == 22 and vardy[0]["match_id"] == 101
    kante = [r for r in positions.to_pylist() if r["player_id"] == 7][0]
    assert kante["to_time"] is None and kante["end_reason"] == "Final Whistle"
    nick = {r["player_id"]: r["player_nickname"] for r in players.to_pylist()}
    assert nick[9] == "Jamie Vardy" and nick[7] is None


def test_flatten_all_writes_one_file_per_competition_and_stats(sb_raw, fields, tmp_path):
    stats = flatten.flatten_all(sb_raw, tmp_path, season_id=27, competition_ids=[2, 7], fields=fields)
    for kind in ("events", "lineup_players", "lineup_positions"):
        assert sorted(p.name for p in (tmp_path / kind).iterdir()) == [
            "competition_2.parquet", "competition_7.parquet"]
    assert pq.read_table(tmp_path / "events/competition_2.parquet").num_rows == 9
    assert pq.read_table(tmp_path / "events/competition_7.parquet").num_rows == 2
    m = pq.read_table(tmp_path / "matches.parquet").to_pylist()
    assert [(r["match_id"], r["competition_id"]) for r in m] == [(101, 2), (201, 7)]
    assert m[1]["data_version"] is None
    assert stats["matches"] == 2 and stats["events"] == 11
    assert stats["peak_rss_bytes"] > 0


def test_flatten_all_stops_if_a_listed_match_has_no_events(sb_raw, fields, tmp_path):
    import shutil
    raw = tmp_path / "raw"
    shutil.copytree(sb_raw, raw)
    (raw / "events/201.json").unlink()
    with pytest.raises(FileNotFoundError):
        flatten.flatten_all(raw, tmp_path / "out", 27, [2, 7], fields)
