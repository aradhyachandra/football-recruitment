"""Publication checks: the StatsBomb logo is the Media Pack file, unchanged, and every doc shows it."""
import hashlib

from recruit import config, report

PUB = config.load("publication")


def test_logo_is_the_media_pack_file_unchanged():
    logo = config.ROOT / PUB["statsbomb_logo"]["path"]
    assert hashlib.sha256(logo.read_bytes()).hexdigest() == PUB["statsbomb_logo"]["sha256"]


def test_every_doc_template_shows_logo_and_season_label_placeholder():
    for t in (config.ROOT / "docs" / "templates").glob("*.md"):
        text = t.read_text(encoding="utf-8")
        assert "{{logo_html}}" in text, t.name
        assert "2015/2016" not in text and "2015/16" not in text, t.name  # label comes from config


def test_publication_context():
    ctx = report.publication_context()
    assert ctx["season_label"] == config.load("scope")["season"]["label"]
    assert PUB["statsbomb_logo"]["path"] in ctx["logo_html"]


def test_nothing_from_data_or_event_level_would_be_committed():
    import subprocess
    git = lambda *a: subprocess.run(["git", *a], cwd=config.ROOT, capture_output=True, text=True, check=True).stdout  # noqa: E731
    files = git("ls-files").split() + git("ls-files", "--others", "--exclude-standard").split()
    assert files, "not a git checkout"
    bad = [f for f in files if f.startswith("data/") or f.endswith((".parquet", ".duckdb", ".csv.gz"))
           or (f.startswith("results/") and not f.endswith(".json"))]
    assert bad == []
    results = [f for f in files if f.startswith("results/")]
    text = " ".join((config.ROOT / f).read_text(encoding="utf-8") for f in results)
    for key in ['"event_id"', '"location"', '"timestamp"', '"match_id"']:  # event-level fields
        assert key not in text
