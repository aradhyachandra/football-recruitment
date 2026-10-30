"""R7: check every number on the portfolio case-study page against results/, and write the check file.

    python -m recruit.portfolio_numbers --site ~/Projects/portfolio-site

The portfolio site is a separate repository; its football page and the football parts of its home page
are written by hand. This script recomputes each figure the page shows from results/*.json (FACTS), checks
that the page shows it exactly as computed, and checks that every number on the page is one of those
figures or a listed label (config/publication.yaml portfolio.number_exempt). It writes
docs/R7_portfolio_numbers.md: each number with its source. It never edits the site.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from recruit import config, report

ROOT = config.ROOT
DOC = ROOT / "docs" / "R7_portfolio_numbers.md"
NUMBER = re.compile(r"\d(?:[\d,]*\d)?(?:\.\d+)?")   # 5,321,459 and 84.5, not a trailing comma


def load() -> dict:
    files = {"r1": "r1_data_report", "r2": "r2_profiles_summary", "r3": "r3_join_summary", "r4": "r4_shortlist",
             "r5": "r5_sensitivity"}
    return {k: json.loads((ROOT / "results" / f"{v}.json").read_text(encoding="utf-8")) for k, v in files.items()}


def m(eur: float) -> str:
    return f"EUR {eur / 1e6:g}m"


def facts(r: dict) -> list[dict]:
    """(what, shown text, source) for every figure the football page and home-page card show."""
    r1, r2, r3, r4, r5 = r["r1"], r["r2"], r["r3"], r["r4"], r["r5"]
    t, s, f = r4["target"], r4["settings"], r5["report_facts"]
    cand = {c["name"]: c for c in r5["candidates"]}
    rec = cand[r5["recommendation"][0]["name"]]
    b1, b2 = (cand[p["name"]] for p in r5["recommendation"][1:3])
    close1, close2 = (cand[c["name"]] for c in f["closest_eligible"][:2])
    prof = {p["label"]: round(100 * (p["pct_rank_padj"] if p["possession_adjusted"] else p["pct_rank"]))
            for p in r2["departing_player"]["profile"]}
    allp = next(x for x in r3["match_rates"] if x["threshold"] == 0 and x["league"] == "All" and x["role"] == "All")
    stab = {k["k"]: k for k in r4["stability"]["top_k"]}
    gw = s["group_weights"]
    vn, vd = rec["value_named"], rec["value_draws"]
    rows = [
        ("Kanté's market value", m(t["market_value_eur"]), "r4_shortlist.json target.market_value_eur"),
        ("Budget cap", m(s["budget_cap_eur"]), "r4_shortlist.json settings.budget_cap_eur"),
        ("Age range", f"{s['age_min']} to {s['age_max']}", "r4_shortlist.json settings.age_min, age_max"),
        ("Valuation date", "1 July 2016" if config.load("scope")["valuation_date"] == "2016-07-01" else "?",
         "config/scope.yaml valuation_date (2016-07-01)"),
        ("Matches", f"{r1['row_counts']['sb_matches']:,}", "r1_data_report.json row_counts.sb_matches"),
        ("Events", f"{r1['row_counts']['sb_events']:,}", "r1_data_report.json row_counts.sb_events"),
        ("Players matched", f"{allp['matched']:,} of {allp['players']:,}", "r3_join_summary.json match_rates (All, threshold 0)"),
        ("Match rate", f"{allp['match_rate']:.2%}", "r3_join_summary.json match_rates (All, threshold 0)"),
        ("Pool size", f"{r4['pool']['pool']}", "r4_shortlist.json pool.pool"),
        ("Minutes threshold", f"{r4['pool']['min_minutes']}+", "r4_shortlist.json pool.min_minutes"),
        *[(f"Kanté percentile: {k}", report.fmt(v, "ord"), "r2_profiles_summary.json departing_player.profile "
           "(pct_rank_padj if possession-adjusted, else pct_rank)")
          for k, v in prof.items() if k in ("Interceptions", "Blocks", "Tackles won", "Progressive carries",
                                            "Shots (excl. penalties)", "Non-penalty xG")],
        ("Metrics", f"{f['n_metrics']} per-90 metrics", "r5_sensitivity.json report_facts.n_metrics"),
        ("Group weights", ", ".join(f"{v:.0%}" for v in gw.values()), "r4_shortlist.json settings.group_weights"),
        ("Value-score weights", f"{s['value_weights']['similarity']:.0%} similarity, {s['value_weights']['price']:.0%} cheapness",
         "r4_shortlist.json settings.value_weights"),
        ("Scenarios", f"{len(r5['scenarios'])} one-change scenarios", "r5_sensitivity.json scenarios (count)"),
        ("Random weightings", f"{r5['draws']['draws']} random weightings", "r5_sensitivity.json draws.draws"),
        ("Closest profile: similarity", f"{close1['similarity']:.1f}", f"r5_sensitivity.json candidates ({close1['name']}).similarity"),
        ("Closest profile: value", m(close1["market_value_eur"]), f"r5_sensitivity.json candidates ({close1['name']})"),
        ("Second closest: value", m(close2["market_value_eur"]), f"r5_sensitivity.json candidates ({close2['name']})"),
        ("Recommended: value", m(rec["market_value_eur"]), f"r5_sensitivity.json candidates ({rec['name']})"),
        ("Recommended: age", f"Sevilla, {rec['age']}" if rec["club"] == "Sevilla" else "?", f"r5_sensitivity.json candidates ({rec['name']}).age"),
        ("Recommended: similarity", f"{rec['similarity']:.1f}", f"r5_sensitivity.json candidates ({rec['name']}).similarity"),
        ("Recommended: similarity rank", report.fmt(rec["similarity_rank"], "ord"), f"r5_sensitivity.json candidates ({rec['name']}).similarity_rank"),
        ("Recommended: minutes", f"{rec['minutes']:,} minutes", f"r5_sensitivity.json candidates ({rec['name']}).minutes"),
        ("Robust core", f"{f['core_size']} players", "r5_sensitivity.json report_facts.core_size"),
        ("Robust core line", f"{f['core_line_scenarios']} of the {len(r5['scenarios'])}", "r5_sensitivity.json report_facts.core_line_scenarios"),
        ("Split-half: players", f"{r4['stability']['players']}", "r4_shortlist.json stability.players"),
        ("Split-half: own profile closest", f"{stab[1]['share']:.1%}", "r4_shortlist.json stability.top_k (k=1)"),
        ("Split-half: own profile in top 5", f"{stab[5]['share']:.1%}", "r4_shortlist.json stability.top_k (k=5)"),
        ("Recommended: top 10 in scenarios", f"{vn['share_top_n'] * vn['scenarios']:.0f} of {vn['scenarios']}",
         f"r5_sensitivity.json candidates ({rec['name']}).value_named"),
        ("Recommended: top 10 in draws", f"{vd['share_top_n']:.0%}", f"r5_sensitivity.json candidates ({rec['name']}).value_draws.share_top_n"),
        ("Recommended: top 3 in scenarios", f"{vn['share_top_k']:.1%}", f"r5_sensitivity.json candidates ({rec['name']}).value_named.share_top_k"),
        ("Backups: value", f"{b1['club']}, {m(b1['market_value_eur'])}", f"r5_sensitivity.json candidates ({b1['name']})"),
        ("Backups: value", f"{b2['club']}, {m(b2['market_value_eur'])}", f"r5_sensitivity.json candidates ({b2['name']})"),
        ("Value top N", f"value top {r5['settings']['top_n']}", "r5_sensitivity.json settings.top_n"),
        ("Value top K", f"top {r5['settings']['top_k']}", "r5_sensitivity.json settings.top_k"),
        ("Shortlist without split-half rank", f"{f['r4_shortlist_no_split_half']} of the {len(r4['shortlist'])}",
         "r5_sensitivity.json report_facts.r4_shortlist_no_split_half; r4_shortlist.json shortlist"),
        ("Cheapest frontier player (chart alt text)", m(min(e["market_value_eur"] for e in r4["frontier"])),
         "r4_shortlist.json frontier (lowest market_value_eur)"),
    ]
    return [{"what": w, "shown": shown, "source": src} for w, shown, src in rows]


def page_text(path: Path, start: str | None = None, end: str | None = None) -> str:
    """Visible text plus alt/content/aria-label attributes; optionally only between two markers."""
    s = path.read_text(encoding="utf-8")
    if start:
        s = s[s.index(start): s.index(end, s.index(start)) if end else None]
    attrs = " ".join(re.findall(r'(?:alt|content|aria-label|title)="([^"]*)"', s))
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S)
    s = re.sub(r'href="[^"]*"|src="[^"]*"|width="\d+"|height="\d+"', " ", s)
    text = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(re.sub(r"\s+", " ", text + " " + attrs))


def check(site: Path) -> dict:
    exempt = config.load("publication")["portfolio"]["number_exempt"]
    rows = facts(load())
    parts = {"projects/football-recruitment.html": page_text(site / "projects" / "football-recruitment.html"),
             "index.html (football card)": page_text(site / "index.html", '<a class="shot" href="/projects/football-recruitment.html"', "</article>"),
             "index.html (results strip)": page_text(site / "index.html", '<a class="kpi" href="/projects/football-recruitment.html"', "</a>")}
    allowed = {tok for r in rows for tok in NUMBER.findall(r["shown"])} | {
        tok for e in exempt for tok in NUMBER.findall(e)}
    for r in rows:
        r["on_page"] = [name for name, text in parts.items() if r["shown"] in text]
    unknown = {name: sorted({tok for tok in NUMBER.findall(text) if tok not in allowed}) for name, text in parts.items()}
    return {"facts": rows, "unknown_numbers": unknown,
            "all_numbers_sourced": not any(unknown.values()),
            "all_facts_shown": all(r["on_page"] for r in rows)}


def render(res: dict) -> str:
    exempt = config.load("publication")["portfolio"]
    table = report.markdown_table(
        [{"w": r["what"], "s": f"`{r['shown']}`", "src": r["source"], "p": ", ".join(r["on_page"]) or "NOT ON PAGE"}
         for r in res["facts"]],
        [("w", "Figure"), ("s", "Shown as"), ("src", "Source (results/ unless stated)"), ("p", "Where")])
    unknown = "; ".join(f"{k}: {', '.join(v)}" for k, v in res["unknown_numbers"].items() if v) or "none"
    return f"""# R7: Numbers on the portfolio case-study page

{report.publication_context()["logo_html"]}

*Generated by `python -m recruit.portfolio_numbers --site <portfolio-site>`. Every figure the football
page (`projects/football-recruitment.html`) and the football parts of the home page show, recomputed from
`results/`, with its source. The site is a separate repository; this file stays here.*

- Every listed figure is on the page exactly as computed: **{"yes" if res["all_facts_shown"] else "NO"}**
- Every number on those parts of the site is a listed figure or a label below: **{"yes" if res["all_numbers_sourced"] else "NO"}**
  (numbers not accounted for: {unknown})

{table}

Labels that contain digits but are not results ({exempt["number_exempt_reason"]}):
{", ".join(f"`{e}`" for e in exempt["number_exempt"])}.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", required=True)
    res = check(Path(ap.parse_args().site).expanduser())
    DOC.write_text(render(res), encoding="utf-8")
    print(f"wrote {DOC.relative_to(ROOT)}; all facts shown: {res['all_facts_shown']}; "
          f"all numbers sourced: {res['all_numbers_sourced']} {res['unknown_numbers']}")


if __name__ == "__main__":
    main()
