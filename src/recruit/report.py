"""Fill doc templates (docs/templates/*.md) from saved results only.

A placeholder is {{a.b.c}} (a value in the context, {{a.b|pct}} as a percentage) or {{table:name}}
(a ready-made markdown table). An unknown placeholder raises, so a doc can never hold a number that is
not in the context. Single braces are left alone (mermaid, code).
"""
from __future__ import annotations

import re

from recruit import config

PLACEHOLDER = re.compile(r"\{\{\s*([\w.\-: |]+?)\s*\}\}")


def fmt(value, style=None) -> str:
    if value is None:
        return ""
    if style == "pct":
        return f"{value:.1%}"
    if style == "plain":  # identifiers such as a seed: no thousands separator
        return str(value)
    if style == "ord":    # 1st, 2nd, 3rd, 11th, 92nd
        n = int(round(value))
        suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"
    if style == "pct2":   # for shares close to 0% or 100%, where one decimal would round away a gap
        return f"{value:.2%}"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def markdown_table(rows: list[dict], columns: list[tuple]) -> str:
    """rows: list of dicts. columns: (key, header) or (key, header, "pct"). Numbers align right."""
    def numeric(key):
        return any(isinstance(r.get(key), (int, float)) and not isinstance(r.get(key), bool) for r in rows)

    lines = ["| " + " | ".join(c[1] for c in columns) + " |",
             "|" + "|".join("---:" if numeric(c[0]) else "---" for c in columns) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(fmt(r.get(c[0]), c[2] if len(c) > 2 else None) for c in columns) + " |")
    return "\n".join(lines)


def _lookup(context: dict, key: str, tables: dict) -> str:
    if key.startswith("table:"):
        name = key[len("table:"):]
        if name not in tables:
            raise KeyError(f"Placeholder {{{{{key}}}}} has no table")
        return tables[name]
    dotted, _, style = key.partition("|")
    value = context
    for part in dotted.split("."):
        if isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise KeyError(f"Placeholder {{{{{dotted}}}}} not found in the context")
    return fmt(value, style or None)


def publication_context(prefix: str = "../") -> dict:
    """Shared by every doc: the season label and the StatsBomb logo tag (config/scope.yaml, publication.yaml).
    prefix: path from the doc to the repo root ("../" for docs/, "" for README.md)."""
    logo = config.load("publication")["statsbomb_logo"]
    return {"season_label": config.season_label(),
            "logo_html": f'<img src="{prefix}{logo["path"]}" alt="Hudl StatsBomb logo" width="{logo["doc_width_px"]}">'}


def render_template(text: str, context: dict, tables: dict | None = None) -> str:
    return PLACEHOLDER.sub(lambda m: _lookup(context, m.group(1), tables or {}), text)
