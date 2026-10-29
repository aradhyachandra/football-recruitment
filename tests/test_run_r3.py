"""R3 summary and doc on the hand-made tables: every template placeholder resolves, rates add up,
and the departing player's Transfermarkt id is enforced."""
import copy

import pytest

from recruit import config, load, market_values, run_r3
from tests import r3_data

CFG = copy.deepcopy(config.load("matching"))
CFG["summary"].update(minutes_thresholds=[0, 300], sample_size=3)   # hand-made players have 90-450 minutes


@pytest.fixture(scope="module")
def built():
    con = load.connect(":memory:", "1GB", 1)
    r3_data.build(con)
    rows = market_values.build(con, r3_data.SCOPE, r3_data.CLUB_MAP, r3_data.OVERRIDES, CFG)
    return con, rows


def summary(built, scope=r3_data.SCOPE):
    con, rows = built
    return run_r3.build_summary(con, scope, CFG, rows, r3_data.CLUB_MAP, r3_data.OVERRIDES)


def test_summary_rates_and_lists(built):
    s = summary(built)
    overall = next(r for r in s["match_rates"] if r["threshold"] == 0 and r["league"] == r["role"] == "All")
    assert (overall["players"], overall["matched"], overall["priced"]) == (10, 8, 4)   # 16 and 19 unmatched
    assert [u["name"] for u in s["unmatched"]] == ["Jonathan Silva Ramos", "Totally Different"]
    assert s["departing_player"]["market_value_eur"] == 20_000_000
    assert s["departing_player"]["valuation_date"] == "2016-06-01"
    assert s["plausibility"]["flagged"] == 1
    assert len(s["sample"]) == 3 and set(s["sample"][0]) == {"statsbomb_name", "statsbomb_team",
                                                            "transfermarkt_name", "transfermarkt_club", "method"}
    assert s["sample"] == summary(built)["sample"]          # fixed seed: same sample every run


def test_wrong_departing_id_stops(built):
    scope = copy.deepcopy(r3_data.SCOPE)
    scope["departing_player_ids"]["transfermarkt_player_id"] = 1099
    with pytest.raises(ValueError, match="expected 1099"):
        summary(built, scope)


def test_doc_renders_from_the_summary(built):
    s = summary(built)
    template = run_r3.TEMPLATE.read_text(encoding="utf-8").replace("all.900", "all.300").replace(
        "valuation_gaps.900", "valuation_gaps.300")
    doc = run_r3.render(s, template)
    assert "{{" not in doc and "N'Golo Kanté" in doc
