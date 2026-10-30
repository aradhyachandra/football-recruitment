"""README.md: rendered from its template and results/ only, up to date, every number in results/, credits,
logo, two-route caveat and screenshots present; LICENSE covers the code only."""
import json
import re

import pytest

from recruit import config, run_r6
from tests.test_report_r5 import numbers_not_in_results

ROOT = config.ROOT
PUB = config.load("publication")
README = ROOT / "README.md"


@pytest.fixture(scope="module")
def rendered():
    if not (ROOT / "results" / "r5_sensitivity.json").exists():
        pytest.skip("run R1-R5 first")
    return run_r6.render()


def _prose(text: str) -> str:
    """README without code blocks, inline code and HTML tags (commands, file names, the logo tag)."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return text


def test_readme_is_up_to_date(rendered):
    text, facts = rendered
    assert README.read_text(encoding="utf-8") == text, "README.md is stale: run python -m recruit.run_r6"
    assert json.loads((ROOT / "results" / "r6_readme.json").read_text(encoding="utf-8")) == facts


def test_every_number_in_readme_is_in_results(rendered):
    text, _ = rendered
    results = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "results").glob("*.json"))]
    assert numbers_not_in_results(_prose(text), results, PUB["readme"]["number_exempt_phrases"]) == []


def test_readme_template_has_no_literal_numbers():
    text = re.sub(r"\{\{[^}]*\}\}", " ", run_r6.TEMPLATE.read_text(encoding="utf-8"))
    assert numbers_not_in_results(_prose(text), [], PUB["readme"]["number_exempt_phrases"]) == []


def test_readme_content(rendered):
    text = " ".join(rendered[0].split())
    for must in ["similar profile under stated assumptions", "Two routes", PUB["author"], "LICENSE",
                 PUB["statsbomb_logo"]["path"], "Media Pack", "transfermarkt-datasets", "statsbomb.com/resource-centre",
                 "python -m recruit.download"]:
        assert must in text, must
    for img in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text):
        assert (ROOT / img).exists(), img
    assert "2015/2016" not in text and "{{" not in text
    for banned in ["would succeed", "proven", "guarantee"]:
        assert banned not in text.lower()


def test_license_is_mit_for_code_only():
    text = " ".join((ROOT / "LICENSE").read_text(encoding="utf-8").split())
    assert text.startswith("MIT License") and PUB["author"] in text
    assert "not covered" in text and "not included" in text and "StatsBomb" in text
