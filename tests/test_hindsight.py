"""No hindsight in public results: no date after the valuation date in results/*.json (run fields exempt)."""
import json

import pytest

from recruit import config
from recruit.hindsight import dates_after

PUB = config.load("publication")["hindsight_check"]
CUTOFF = config.load("scope")["valuation_date"]
RESULTS = sorted((config.ROOT / "results").glob("*.json"))


def test_finds_later_dates_and_skips_exempt_keys():
    obj = {"a": "2016-07-01", "b": [{"date": "2016-08-01"}, "seen 2017-02-20T10:00"],
           "run": {"finished": "2026-10-29T17:00:00"}, "c": 20160801, "d": "2015/16"}
    hits = dates_after(obj, "2016-07-01", exempt_keys=["run"])
    assert hits == [("b[0].date", "2016-08-01"), ("b[1]", "seen 2017-02-20T10:00")]


def test_flags_negative_days_before():
    obj = {"history": [{"days_before": 30}, {"days_before": -31}], "other_days": -5}
    assert dates_after(obj, "2016-07-01", negative_day_keys=["days_before"]) == [("history[1].days_before", "-31")]


def test_results_folder_has_files():
    assert RESULTS, "results/*.json missing"


@pytest.mark.parametrize("path", RESULTS, ids=lambda p: p.name)
def test_no_date_after_valuation_date_in_results(path):
    hits = dates_after(json.loads(path.read_text(encoding="utf-8")), CUTOFF,
                       PUB["exempt_keys"], PUB["negative_day_keys"])
    assert hits == [], f"{path.name} holds information dated after {CUTOFF}: {hits[:5]}"
