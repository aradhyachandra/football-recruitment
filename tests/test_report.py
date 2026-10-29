"""Template filling: every placeholder must resolve from saved results, or rendering fails."""
import pytest

from recruit import report


def test_values_tables_and_formats():
    ctx = {"a": {"n": 1234567, "share": 0.8123, "x": 2.5, "ok": True}, "rows": [{"v": "first"}]}
    text = "{{a.n}} | {{a.share|pct}} | {{a.x}} | {{a.ok}} | {{rows.0.v}} | {single}\n{{table:t}}"
    out = report.render_template(text, ctx, {"t": "|x|"})
    assert out == "1,234,567 | 81.2% | 2.50 | True | first | {single}\n|x|"


def test_unknown_placeholder_raises():
    with pytest.raises(KeyError):
        report.render_template("{{a.missing}}", {"a": {}})
    with pytest.raises(KeyError):
        report.render_template("{{table:nope}}", {})


def test_markdown_table_aligns_numbers_right():
    t = report.markdown_table([{"k": "x", "n": 3, "s": 0.5}], [("k", "Key"), ("n", "N"), ("s", "Share", "pct")])
    assert t.splitlines() == ["| Key | N | Share |", "|---|---:|---:|", "| x | 3 | 50.0% |"]
