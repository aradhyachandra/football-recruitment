"""R4 figures (static PNG for docs/figures/): similarity vs market value with the frontier and the
shortlist labelled, and Kante's percentile profile against the top of the shortlist.
Colours: reference palette of the dataviz guidance (light surface; first three categorical slots)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#b5b4ad", "#e6e5e0"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
CREDIT = "Data: StatsBomb Open Data (2015/16 events); market values: transfermarkt-datasets (CC0)."
STALE_NOTE = "* valuation older than 183 days at 2016-07-01 (flagged, kept)"


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _name(e):
    return e["name"] + ("*" if e["valuation_stale"] else "")


def scatter(res: dict, s: dict, cfg: dict, path: Path) -> None:
    """Priced candidates; frontier and shortlist marked and numbered (cheapest first), names in a key."""
    t = res["table"]
    cand = t[~t["is_target"] & t["market_value_eur"].notna()]
    front = {e["statsbomb_player_id"] for e in s["frontier"]}
    short = {e["statsbomb_player_id"] for e in s["shortlist"]}
    fig = plt.figure(figsize=(13, 7.2), facecolor=SURFACE)
    ax = fig.add_axes((0.06, 0.12, 0.62, 0.8))
    key = fig.add_axes((0.70, 0.12, 0.29, 0.8))
    key.axis("off")
    _style(ax)
    ax.set_xscale("log")
    other = cand[~cand.index.isin(front | short)]
    ax.scatter(other["market_value_eur"], other["similarity"], s=22, color=MUTED, edgecolor=SURFACE,
               linewidth=0.8, label=f"Other priced {s['pool']['role'].lower()}s", zorder=2)
    f = cand[cand.index.isin(front)]
    ax.scatter(f["market_value_eur"], f["similarity"], s=48, color=SERIES[0], edgecolor=SURFACE, linewidth=1.5,
               label="Frontier: no one both more similar and cheaper", zorder=3)
    sl = cand[cand.index.isin(short)]
    ax.scatter(sl["market_value_eur"], sl["similarity"], s=170, facecolor="none", edgecolor=SERIES[1], linewidth=2,
               label="Shortlist: top 10 value score within constraints", zorder=4)
    cap = cfg["constraints"]["budget_cap_eur"]
    ax.axvline(cap, color=INK2, linestyle=(0, (4, 3)), linewidth=1, zorder=1)
    ax.text(cap * 1.05, ax.get_ylim()[1] - 0.3, f"budget cap\nEUR {cap / 1e6:g}m", color=INK2, fontsize=8.5,
            va="top")
    labelled = {e["statsbomb_player_id"]: e for e in s["frontier"] + s["shortlist"]}
    items = sorted(labelled.values(), key=lambda e: (e["market_value_eur"], -e["similarity"]))
    lines, done = [], []
    for i, e in enumerate(items, 1):
        x, y = e["market_value_eur"], e["similarity"]
        crowded = any(abs(x / px - 1) < 0.15 and abs(y - py) < 1.0 for px, py in done)   # put the second to the left
        done.append((x, y))
        ax.annotate(str(i), (x, y), xytext=(-16, 5) if crowded else (6, 5), textcoords="offset points",
                    fontsize=8, color=INK, fontweight="bold", zorder=5)
        tags = ("F" if e["statsbomb_player_id"] in front else "-") + ("S" if e["statsbomb_player_id"] in short else "-")
        lines.append(f"{i:>2}  {tags}  {_name(e)[:24]:<24} {e['market_value_eur'] / 1e6:5.2f}m  {e['similarity']:.1f}")
    key.text(0, 1, "#   F=frontier S=shortlist\n    player                  value   similarity\n\n" + "\n".join(lines),
             family="monospace", fontsize=8, color=INK, va="top")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1e6:g}m"))
    ax.set_xlabel("Market value at 2016-07-01 (EUR, log scale)", color=INK2)
    ax.set_ylabel(f"Similarity to {s['target']['name']} (0-100)", color=INK2)
    ax.set_title(f"Similar profile vs price: {s['pool']['role']}s, {s['pool']['min_minutes']}+ minutes, 2015/16",
                 loc="left", color=INK, fontsize=12)
    ax.legend(loc="lower left", fontsize=8.5, frameon=False, labelcolor=INK2)
    fig.text(0.01, 0.035, CREDIT, fontsize=7.5, color=INK2)
    fig.text(0.01, 0.012, "Similar profile under stated assumptions (config/similarity.yaml), not a forecast. "
             + STALE_NOTE, fontsize=7.5, color=INK2)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def profiles(s: dict, cfg: dict, path: Path) -> None:
    n = cfg["outputs"]["figure_top_profiles"]
    people = [s["target"]] + s["shortlist"][:n]
    metrics = list(s["target"]["percentiles"])
    fig, ax = plt.subplots(figsize=(10, 6.5), facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="y", visible=False)
    ys = range(len(metrics))[::-1]
    offsets = [0.27, 0.09, -0.09, -0.27]
    for i, e in enumerate(people):
        vals = [100 * e["percentiles"][m] for m in metrics]
        style = dict(marker="D", s=70, color=INK, zorder=4) if i == 0 else \
            dict(marker="o", s=60, color=SERIES[i - 1], edgecolor=SURFACE, linewidth=1.2, zorder=3)
        label = (f"{e['name']} (target)" if i == 0 else
                 f"#{i} {_name(e)}, {e['club']}, similarity {e['similarity']:.1f}")
        ax.scatter(vals, [y + offsets[i] for y in ys], label=label, **style)
    for y in ys:
        ax.axhline(y, color=GRID, linewidth=0.8, zorder=1)
    ax.set_yticks(list(ys), [m.replace("_", " ") for m in metrics], color=INK)
    ax.set_xlim(-2, 102)
    ax.set_xlabel(f"Percentile rank within the {s['pool']['role'].lower()} pool (possession-adjusted for "
                  "defensive metrics)", color=INK2)
    ax.set_title(f"{s['target']['name']} vs the top {n} of the value shortlist", loc="left", color=INK, fontsize=12)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=8.5, frameon=False,
              labelcolor=INK2)
    fig.text(0.01, 0.01, CREDIT + "  Similar profile under stated assumptions, not a forecast.",
             fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def draw(res: dict, s: dict, cfg: dict, out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    a, b = out_dir / "r4_similarity_vs_value.png", out_dir / "r4_profile_comparison.png"
    scatter(res, s, cfg, a)
    profiles(s, cfg, b)
    return [p.relative_to(out_dir.parent.parent).as_posix() for p in (a, b)]
