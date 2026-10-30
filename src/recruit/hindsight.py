"""No-hindsight check for public results: find dates after the valuation date in a JSON-like object.

Exempt keys (run-time fields) and the "negative days before" rule come from config/publication.yaml.
"""
from __future__ import annotations

import re

DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})")


def dates_after(obj, cutoff: str, exempt_keys=(), negative_day_keys=(), path: str = "") -> list[tuple[str, str]]:
    """(path, offending value) for every ISO date string later than `cutoff` and every negative value
    under a key in `negative_day_keys`. Subtrees under `exempt_keys` are skipped."""
    hits: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in exempt_keys:
                continue
            sub = f"{path}.{k}" if path else str(k)
            if k in negative_day_keys and isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0:
                hits.append((sub, str(v)))
            hits += dates_after(v, cutoff, exempt_keys, negative_day_keys, sub)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += dates_after(v, cutoff, exempt_keys, negative_day_keys, f"{path}[{i}]")
    elif isinstance(obj, str):
        hits += [(path, obj) for d in DATE.findall(obj) if d > cutoff]
    return hits
