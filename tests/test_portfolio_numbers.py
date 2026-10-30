"""Portfolio number check (src/recruit/portfolio_numbers.py) on a hand-made site folder."""
from recruit import portfolio_numbers as pn


def make_site(tmp_path, extra=""):
    rows = pn.facts(pn.load())
    body = " · ".join(r["shown"] for r in rows)
    (tmp_path / "projects").mkdir(parents=True)
    (tmp_path / "projects" / "football-recruitment.html").write_text(
        f'<html><head><meta content="1200"><style>.a{{width:999px}}</style></head><body><p>Case study 04 · 2015/16</p>'
        f'<img src="/x-77.png" width="1300" alt="chart">{body} {extra}</body></html>', encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<a class="kpi" href="/projects/football-recruitment.html"><span>16/16</span></a>'
        '<a class="shot" href="/projects/football-recruitment.html">307 central midfielders</a></article>',
        encoding="utf-8")
    return tmp_path


def test_facts_come_from_results():
    rows = pn.facts(pn.load())
    assert rows and all("?" not in r["shown"] and r["source"] for r in rows)
    shown = {r["what"]: r["shown"] for r in rows}
    assert shown["Kanté's market value"] == "EUR 20m" and shown["Pool size"] == "307"


def test_page_text_drops_markup_but_keeps_alt_text(tmp_path):
    f = tmp_path / "p.html"
    f.write_text('<p>A <b>1,503</b> minutes</p><img src="/a-12.png" width="400" alt="EUR 4m dot"><style>p{x:9}</style>')
    text = pn.page_text(f)
    assert "1,503 minutes" in text and "EUR 4m dot" in text
    assert "12" not in pn.NUMBER.findall(text) and "400" not in text and "9" not in pn.NUMBER.findall(text)


def test_check_passes_and_catches_an_unsourced_number(tmp_path):
    ok = pn.check(make_site(tmp_path / "a"))
    assert ok["all_facts_shown"] and ok["all_numbers_sourced"]
    bad = pn.check(make_site(tmp_path / "b", extra="and 42% more"))
    assert not bad["all_numbers_sourced"]
    assert bad["unknown_numbers"]["projects/football-recruitment.html"] == ["42"]
    assert "NO" in pn.render(bad)
