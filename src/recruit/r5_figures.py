"""R5 figures (static PNG for docs/figures/): how often each main candidate is in the value top 10 per
scenario (with his rank), and his rank range across the named scenarios and the random weight draws.
Same palette and credit line as the R4 figures."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from recruit.r4_figures import CREDIT, GRID, INK, INK2, MUTED, SERIES, SURFACE, _style  # noqa: E402

NOTE = "Similar profile under stated assumptions (config/similarity.yaml, config/sensitivity.yaml), not a forecast."


def main_candidates(s: dict, min_share: float) -> list[dict]:
    return [c for c in s["candidates"]
            if max(c["value_named"]["share_top_n"], c["value_draws"]["share_top_n"]) >= min_share]


def _q(s):
    lo, hi = (round(100 * q) for q in s["settings"]["draw_rank_quantiles"])
    return f"{lo}th-{hi}th"


def _label(c):
    return c["name"] + ("*" if c.get("valuation_stale") else "") + (" (core)" if c["in_core"] else "")


def heatmap(s: dict, people: list[dict], path: Path) -> None:
    n = s["settings"]["top_n"]
    scen = s["scenarios"]
    fig_h = 0.4 * len(people)
    total = fig_h + 4.2          # room for the rotated scenario labels below and a two-line title above
    fig = plt.figure(figsize=(15, total), facecolor=SURFACE)
    ax = fig.add_axes((0.2, 3.1 / total, 0.72, fig_h / total))
    cmap = LinearSegmentedColormap.from_list("rank", [SERIES[0], "#cfe0f5"])
    for i, c in enumerate(people):
        for j, sc in enumerate(scen):
            r = c["named_value_ranks"].get(sc["id"])
            if r is None:
                ax.add_patch(plt.Rectangle((j, i), 1, 1, color=SURFACE, ec=GRID))
                ax.text(j + 0.5, i + 0.5, "-", ha="center", va="center", fontsize=8, color=MUTED)
            elif r <= n:
                ax.add_patch(plt.Rectangle((j, i), 1, 1, color=cmap((r - 1) / max(n - 1, 1)), ec=SURFACE))
                ax.text(j + 0.5, i + 0.5, str(int(r)), ha="center", va="center", fontsize=8,
                        color=SURFACE if r <= n / 2 else INK)
            else:
                ax.add_patch(plt.Rectangle((j, i), 1, 1, color="#f1f0ec", ec=SURFACE))
        for j, (key, colr) in enumerate((("value_named", INK), ("value_draws", INK2))):
            x = len(scen) + 0.3 + j * 1.3
            ax.text(x + 0.6, i + 0.5, f"{c[key]['share_top_n']:.0%}", ha="center", va="center", fontsize=8.5,
                    color=colr)
    ax.set_xlim(0, len(scen) + 2.9)
    ax.set_ylim(len(people), 0)
    ax.set_yticks([i + 0.5 for i in range(len(people))], [_label(c) for c in people], fontsize=8.5, color=INK)
    ax.set_xticks([j + 0.5 for j in range(len(scen))] + [len(scen) + 0.9, len(scen) + 2.2],
                  [sc["label"] for sc in scen] + ["Named\nscenarios", "Random\nweights"],
                  rotation=60, ha="right", fontsize=8, color=INK2)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title(f"Value rank when in the top {n}, by scenario (blank: ranked below {n}; -: not eligible or "
                 f"not in the pool)\nRight: share of the named scenarios and of the {s['draws']['draws']} "
                 f"random weight draws with the player in the top {n}", loc="left", color=INK, fontsize=10.5)
    fig.text(0.01, 0.03, CREDIT, fontsize=7.5, color=INK2)
    fig.text(0.01, 0.012, NOTE + "  * stale valuation (flagged, kept in the base case).", fontsize=7.5, color=INK2)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def rank_ranges(s: dict, people: list[dict], path: Path) -> None:
    n = s["settings"]["top_n"]
    fig, ax = plt.subplots(figsize=(11, 1.8 + 0.42 * len(people)), facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="y", visible=False)
    for i, c in enumerate(people):
        a, d = c["value_named"], c["value_draws"]
        if a.get("min_rank") is not None:
            ax.plot([a["min_rank"], a["max_rank"]], [i - 0.12] * 2, color=SERIES[0], linewidth=2.2, zorder=2)
            ax.scatter([a["median_rank"]], [i - 0.12], color=SERIES[0], s=40, zorder=3, edgecolor=SURFACE,
                       label="Named scenarios: median, full range" if i == 0 else None)
        if d.get("p05_rank") is not None:
            ax.plot([d["p05_rank"], d["p95_rank"]], [i + 0.12] * 2, color=SERIES[1], linewidth=2.2, zorder=2)
            ax.scatter([d["median_rank"]], [i + 0.12], color=SERIES[1], s=40, marker="s", zorder=3,
                       edgecolor=SURFACE, label=f"Random weights: median, {_q(s)} percentile" if i == 0 else None)
    ax.axvline(n + 0.5, color=INK2, linestyle=(0, (4, 3)), linewidth=1)
    ax.text(n + 0.8, -0.6, f"top {n}", color=INK2, fontsize=8.5, va="bottom")
    ax.set_yticks(range(len(people)), [_label(c) for c in people], fontsize=8.5, color=INK)
    ax.set_ylim(len(people) - 0.4, -0.8)
    ax.set_xlim(0, None)
    ax.set_xlabel("Value rank among eligible candidates (1 = first)", color=INK2)
    ax.set_title("Rank ranges across the sensitivity scenarios", loc="left", color=INK, fontsize=12)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, fontsize=8.5, frameon=False,
              labelcolor=INK2)
    fig.text(0.01, 0.01, CREDIT + "  " + NOTE, fontsize=7, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def draw(s: dict, min_share: float, out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    people = main_candidates(s, min_share)
    a, b = out_dir / "r5_top10_by_scenario.png", out_dir / "r5_rank_ranges.png"
    heatmap(s, people, a)
    rank_ranges(s, people, b)
    return [p.relative_to(out_dir.parent.parent).as_posix() for p in (a, b)]
