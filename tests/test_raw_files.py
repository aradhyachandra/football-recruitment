"""Raw-file fingerprints: recorded once, then every run stops if a file changed."""
import shutil

import pytest

from recruit import raw_files


def test_csv_rows_and_file_fingerprint(tm_raw):
    fp = raw_files.fingerprint_transfermarkt(tm_raw, ["players", "appearances"], suffix=".csv")
    assert fp["players"]["file"] == "players.csv"
    assert fp["players"]["data_rows"] == 5
    assert fp["appearances"]["data_rows"] == 6
    assert len(fp["players"]["sha256"]) == 64 and fp["players"]["bytes"] > 0


def test_statsbomb_groups_per_competition(sb_raw):
    fp = raw_files.fingerprint_statsbomb(sb_raw, season_id=27, competition_ids=[2, 7])
    assert set(fp) == {"competitions", "matches_2", "events_2", "lineups_2",
                       "matches_7", "events_7", "lineups_7"}
    assert fp["competitions"]["files"] == 1 and fp["competitions"]["records"] == 2
    assert fp["matches_2"]["records"] == 1
    assert fp["events_2"]["files"] == 1 and fp["events_2"]["records"] == 9
    assert fp["events_7"]["records"] == 2
    assert fp["lineups_2"]["records"] == 2  # one record per team
    # without record counting (the verify path) the hashes are the same
    quick = raw_files.fingerprint_statsbomb(sb_raw, 27, [2, 7], count_records=False)
    assert quick["events_2"]["sha256"] == fp["events_2"]["sha256"]
    assert "records" not in quick["events_2"]


def test_verify_passes_then_stops_on_a_changed_file(sb_raw, tm_raw, tmp_path):
    sb = tmp_path / "sb"
    shutil.copytree(sb_raw, sb)
    expected = {"statsbomb": raw_files.fingerprint_statsbomb(sb, 27, [2, 7]),
                "transfermarkt": raw_files.fingerprint_transfermarkt(tm_raw, ["clubs"], suffix=".csv")}
    out = tmp_path / "raw_files.yaml"
    raw_files.write_fingerprints(expected, out)
    recorded = raw_files.read_fingerprints(out)
    assert recorded == expected
    raw_files.verify(sb, tm_raw, 27, [2, 7], ["clubs"], recorded, suffix=".csv")
    (sb / "events/201.json").write_text("[]")
    with pytest.raises(ValueError, match="events_7"):
        raw_files.verify(sb, tm_raw, 27, [2, 7], ["clubs"], recorded, suffix=".csv")
