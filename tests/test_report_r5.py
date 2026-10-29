"""R5 docs: ordinal and plain formats, trade-off selection, the number check (every number in the
report is in results/), the wording rules, and the figures and docs on the hand-made pool."""
import json
import re

import pytest

from recruit import config, report, report_r5, r5_figures
from recruit import sensitivity as sens
from tests.test_run_r4 import CFG, METRICS_CFG, make_inputs
from tests.test_sensitivity import SMALL

SENS = config.load("sensitivity")
NUMBER = re.compile(r"(?<![A-Za-z\d.])\d[\d,]*(?:\.\d+)?(?!\d)")


# ---------- the number check ----------

def _candidates(obj, out):
    """Every number in a results file: numeric values and the digits inside text values."""
    if isinstance(obj, dict):
        for v in obj.values():
            _candidates(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _candidates(v, out)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        out.update(float(x) for x in re.findall(r"\d+(?:\.\d+)?", obj))
    return out


def numbers_not_in_results(text: str, results: list, exempt: list[str]) -> list[str]:
    """Numbers in the text that no results value explains. A token with d decimals is explained by a
    value v when v, v x 100 (a share shown as a percentage) or v / 1e6 (EUR shown in millions) prints
    the same at d decimals. Exempt phrases, link/image targets, numbered-list markers and table rules
    are removed first."""
    for phrase in exempt:
        text = text.replace(phrase, " ")
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = re.sub(r"(?m)^\s*\d+\.\s", " ", text)
    cands = set()
    for r in results:
        _candidates(r, cands)
    scaled = {c * f for c in cands for f in (1, 100, 1e-6)}
    bad = []
    for tok in NUMBER.findall(text):
        t = tok.replace(",", "")
        d = len(t.split(".")[1]) if "." in t else 0
        want = f"{float(t):.{d}f}"
        if not any(f"{c:.{d}f}" == want for c in scaled):
            bad.append(tok)
    return bad


def test_number_check_catches_an_invented_number():
    res = [{"share": 0.8125, "value": 1500000, "date": "2016-07-01", "n": 1234}]
    ok = "81.2% of players, EUR 1.50m, valued 2016-07-01, n = 1,234.\n1. a list item"
    assert numbers_not_in_results(ok, res, []) == []
    assert numbers_not_in_results("a share of 77.7%", res, []) == ["77.7"]
    assert numbers_not_in_results("per 90 minutes", res, ["per 90"]) == []
    assert numbers_not_in_results("![x](figures/r5_top10.png)", res, []) == []


# ---------- formats and trade-offs ----------

def test_ordinal_and_plain_formats():
    assert [report.fmt(n, "ord") for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 92, 101)] == \
        ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "92nd", "101st"]
    assert report.fmt(20160701, "plain") == "20160701"


def test_tradeoffs_largest_gaps_first():
    target = {"percentiles": {"a": 0.9, "b": 0.5, "c": 0.2, "d": 0.6}}
    player = {"percentiles": {"a": 0.4, "b": 0.55, "c": 0.5, "d": 0.6}}
    out = report_r5.tradeoffs(player, target, {"a": "Alpha"}, 2)
    assert [x["metric"] for x in out] == ["a", "c"]
    assert out[0] == {"metric": "a", "label": "Alpha", "player_pct": 40, "target_pct": 90, "direction": "below"}
    assert out[1]["direction"] == "above"


# ---------- wording ----------

def _forbidden(text):
    return [p for p in SENS["report"]["forbidden_phrases"] if p in text.lower()]


def test_wording_check_catches_forbidden_phrases():
    assert _forbidden("This player would succeed, guaranteed.") == ["would succeed", "guarantee"]


@pytest.mark.parametrize("name", ["REPORT.md", "R5_sensitivity.md"])
def test_templates_follow_the_wording_rules(name):
    text = (report_r5.TEMPLATES / name).read_text(encoding="utf-8")
    assert _forbidden(text) == []
    assert "similar profile under stated assumptions" in text.lower()
    assert "StatsBomb" in text


def test_report_template_has_no_literal_numbers():
    """Outside placeholders, the report template holds no figures (exempt phrases and list markers aside)."""
    text = (report_r5.TEMPLATES / "REPORT.md").read_text(encoding="utf-8")
    text = re.sub(r"\{\{[^}]*\}\}", " ", text)
    assert numbers_not_in_results(text, [], SENS["report"]["number_exempt_phrases"]) == []


# ---------- the rendered report on the real results (skipped before R5 has run) ----------

RESULT_FILES = ["r1_data_report", "r2_profiles_summary", "r3_join_summary", "r4_shortlist", "r5_sensitivity"]


def _rendered():
    path = report_r5.DOCS / "REPORT.md"
    if not (path.exists() and (report_r5.RESULTS / "r5_sensitivity.json").exists()):
        pytest.skip("run python -m recruit.run_r5 first")
    return path.read_text(encoding="utf-8")


def test_rendered_report_numbers_all_in_results():
    text = _rendered()
    results = [json.loads((report_r5.RESULTS / f"{n}.json").read_text(encoding="utf-8")) for n in RESULT_FILES]
    assert numbers_not_in_results(text, results, SENS["report"]["number_exempt_phrases"]) == []


def test_rendered_docs_wording_and_completeness():
    text = _rendered()
    note = (report_r5.DOCS / "R5_sensitivity.md").read_text(encoding="utf-8")
    for doc in (text, note):
        assert _forbidden(doc) == [] and "{{" not in doc and "StatsBomb" in doc
    for section in ("## Executive summary", "## The situation", "## What Kanté contributed",
                    "## Method in plain language", "## Similar players and the value view", "## Robustness",
                    "## Recommendation and backups", "## Limits", "## Data sources and terms"):
        assert section in text
    summary = text.split("## Executive summary")[1].split("---")[0]
    assert summary.count("\n- ") == 5
    s = json.loads((report_r5.RESULTS / "r5_sensitivity.json").read_text(encoding="utf-8"))
    assert s["recommendation"][0]["name"] in summary


# ---------- figures and docs on the hand-made pool ----------

def test_figures_on_hand_made_summary(tmp_path):
    out = sens.run(*make_inputs(), CFG, SMALL, METRICS_CFG)
    s = {"settings": {"top_n": SMALL["views"]["top_n"], "top_k": SMALL["views"]["top_k"],
                      "draw_rank_quantiles": SMALL["outputs"]["draw_rank_quantiles"]},
         **sens.summarise(out, CFG, SMALL)}
    assert r5_figures.main_candidates(s, 1.01) == []
    files = r5_figures.draw(s, 0.0, tmp_path / "docs" / "figures")
    assert all((tmp_path / f).stat().st_size > 10_000 for f in files)
