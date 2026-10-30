"""Replacing Kante on a budget: local dashboard. Run with:  streamlit run app/streamlit_app.py

Reads results/ (committed summaries) and data/processed/ (built locally by R1-R3 from your own
StatsBomb and transfermarkt-datasets download; the StatsBomb data may not be redistributed, so this app
is not deployed). The Explore view reruns the tested R4 functions (recruit.dashboard -> run_r4.analyse);
nothing here has maths of its own. Every list is a similar profile under stated assumptions, not a
forecast of how a player would do at another club.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))      # works without `pip install -e .`

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from recruit import config  # noqa: E402
from recruit import dashboard as dash  # noqa: E402

PUB = config.load("publication")
DASH = PUB["dashboard"]
PROCESSED = Path(os.environ.get(DASH["processed_dir_env"], ROOT / "data" / "processed"))
SIM_CFG = config.load("similarity")
SCOPE = config.load("scope")
SEASON = config.season_label()
WORDING = PUB["wording"]["similar"]
VAL_DATE = SCOPE["valuation_date"]
STALE_DAYS = config.load("matching")["valuation"]["max_gap_days"]
COLOR = {"Shortlist": "#2a78d6", "Frontier only": "#eb6834", "Other pool players": "#b5b4ad"}
GROUP_LABEL = {"ball_winning": "Ball winning", "progression": "Progression", "passing_security": "Passing security",
               "attacking_output": "Attacking output"}

st.set_page_config(page_title="Replacing Kanté on a budget", layout="wide")


@st.cache_data
def results():
    return dash.load_results(ROOT)


@st.cache_data
def inputs(processed: str):
    return dash.load_inputs(Path(processed), SCOPE)


@st.cache_data
def pool_table(processed: str):
    path = Path(processed) / "r4" / "r4_similarity.parquet"
    return pd.read_parquet(path) if path.exists() else None


@st.cache_data
def explore(processed: str, player_id: int, weights: tuple, budget: float, ages: tuple):
    players, season = inputs(processed)
    res = dash.explore(players, season, SIM_CFG, config.load("metrics"), player_id, dict(weights), budget, ages)
    return {"similar": dash.similar_players(res), "shortlist": dash.value_shortlist(res),
            "profile": dash.percentile_profile(res, res["config"], config.load("metrics")),
            "counts": res["counts"]}


def percentile_chart(df: pd.DataFrame, title: str):
    base = alt.Chart(df).encode(
        y=alt.Y("Metric:N", sort=list(df["Metric"]), title=None, axis=alt.Axis(labelOverlap=False, labelLimit=220)),
        x=alt.X("Percentile:Q", scale=alt.Scale(domain=[0, 100]), title="Percentile within the role pool"),
        tooltip=["Metric", alt.Tooltip("Value:Q", format=".2f"), alt.Tooltip("Pool median:Q", format=".2f"),
                 alt.Tooltip("Percentile:Q", format=".0f"), "Possession-adjusted"])
    bars = base.mark_bar(color="#2a78d6", cornerRadiusEnd=3)
    median = alt.Chart(pd.DataFrame({"x": [50]})).mark_rule(color="#52514e", strokeDash=[4, 3]).encode(x="x:Q")
    return (bars + median).properties(title=title, height=30 * len(df))


def money(df: pd.DataFrame) -> dict:
    return {"Market value (EUR m)": st.column_config.NumberColumn(format="%.2f")}


r = results()
r4, r5 = r["r4"], r["r5"]
target = r4["target"]

# ---------- header ----------
head_l, head_r = st.columns([4, 1])
with head_l:
    st.title(f"Replacing {target['name']} on a budget")
    st.markdown(
        f"Leicester City, summer 2016. Which central midfielders in the four big leagues had a "
        f"**{WORDING}** to {target['name']}'s {SEASON} season, and which of them were affordable? "
        f"Every list here is a {WORDING}, not a forecast of how a player would do at Leicester.")
with head_r:
    st.image(str(ROOT / PUB["statsbomb_logo"]["path"]), width=180)
    st.caption("Logo: StatsBomb Media Pack")

case_tab, explore_tab = st.tabs([f"Case: replacing {target['name']}", "Explore any player"])

# ---------- Case view (results/ only) ----------
with case_tab:
    s = r4["settings"]
    st.subheader(f"What {target['name']} contributed, against his role pool")
    st.markdown(
        f"{target['name']}: {target['minutes']:,} league minutes for {target['club']}, market value "
        f"EUR {target['market_value_eur'] / 1e6:.0f}m on {target['valuation_date']}. Pool: the "
        f"{r4['pool']['pool']} {r4['pool']['role'].lower()}s with {r4['pool']['min_minutes']}+ minutes. "
        "Defensive actions are adjusted for team possession. The dashed line is the pool median.")
    prof = dash.case_profile(r["r2"])
    c1, c2 = st.columns([3, 2])
    c1.altair_chart(percentile_chart(prof, f"{target['name']}, {SEASON}"), width="stretch")
    c2.dataframe(prof, hide_index=True, width="stretch",
                 column_config={"Value": st.column_config.NumberColumn("Per 90 (or share)", format="%.2f"),
                                "Pool median": st.column_config.NumberColumn(format="%.2f"),
                                "Percentile": st.column_config.NumberColumn(format="%.0f")})

    st.subheader("Similar profile against price (R4)")
    st.markdown(
        f"Each point is a priced candidate in the pool. The **frontier** holds players for whom nobody "
        f"is both more similar and cheaper; the **shortlist** is the top {len(r4['shortlist'])} by value score "
        f"(similarity {s['value_weights']['similarity']:.0%}, cheapness {s['value_weights']['price']:.0%}) within "
        f"EUR {s['budget_cap_eur'] / 1e6:.0f}m and ages {s['age_min']}-{s['age_max']}, excluding Leicester.")
    pts = dash.case_scatter_points(r4, pool_table(str(PROCESSED)))
    scatter = alt.Chart(pts).mark_circle(size=70, opacity=0.85).encode(
        x=alt.X("Similarity:Q", scale=alt.Scale(zero=False), title=f"Similarity to {target['name']} (0-100)"),
        y=alt.Y("Market value (EUR m):Q", scale=alt.Scale(type="log"), title="Market value, EUR m (log scale)"),
        color=alt.Color("Group:N", scale=alt.Scale(domain=list(COLOR), range=list(COLOR.values())),
                        legend=alt.Legend(orient="bottom", title=None)),
        tooltip=["Player", "Club", "Age", alt.Tooltip("Similarity:Q", format=".1f"),
                 alt.Tooltip("Market value (EUR m):Q", format=".2f"), "Value rank", "On frontier", "Stale valuation"])
    cap = alt.Chart(pd.DataFrame({"y": [s["budget_cap_eur"] / 1e6]})).mark_rule(
        color="#52514e", strokeDash=[4, 3]).encode(y="y:Q")
    st.altair_chart((scatter + cap).properties(height=420), width="stretch")
    if pool_table(str(PROCESSED)) is None:
        st.caption("Only the saved shortlist and frontier are shown: the other pool players need "
                   "data/processed/ (see the Explore tab).")

    st.subheader("Robustness (R5): the robust core")
    st.markdown(
        f"The analysis was rerun under {len(r5['scenarios'])} "
        f"one-change scenarios and {r5['draws']['draws']} random group weightings. The robust core is the "
        f"players in the value top {r5['settings']['top_n']} in at least "
        f"{r5['settings']['robust_core_min_share']:.0%} of the scenarios; the recommendation rule was fixed "
        "before any result was seen.")
    st.dataframe(dash.robust_core_table(r5), hide_index=True, width="stretch",
                 column_config=money(None) | {c: st.column_config.NumberColumn(format="%.2f")
                                              for c in dash.robust_core_table(r5).columns if "share" in c})
    rec = r5["recommendation"]
    closest = [c["name"] for c in r5["report_facts"]["closest_eligible"][:2]]
    st.info(
        f"**Two routes.** The pre-set rule recommends **{rec[0]['name']}** (backups: "
        f"{', '.join(p['name'] for p in rec[1:])}): the most profile per euro. He wins on price as much as on "
        f"profile. If the club wants the closest profile it can afford, the most similar players inside the "
        f"constraints are **{' and '.join(closest)}**. Scouting, medical, wage and character checks are outside "
        "this analysis.")

# ---------- Explore view (data/processed/) ----------
with explore_tab:
    if not dash.processed_available(PROCESSED):
        st.info(
            "The Explore view needs `data/processed/`, built on your machine from your own download "
            "(the StatsBomb data may not be redistributed). Register at statsbomb.com/resource-centre, then run:\n\n"
            "```\n.venv/bin/python -m recruit.download\n.venv/bin/python -m recruit.run_r1 --record\n"
            ".venv/bin/python -m recruit.run_r2\n.venv/bin/python -m recruit.run_r3\n.venv/bin/python -m recruit.run_r4\n```\n\n"
            "See the README (Reproduce).")
    else:
        players, _ = inputs(str(PROCESSED))
        sel = dash.selectable_players(players, SIM_CFG["pool"]["min_minutes"])
        labels = list(sel["label"])
        default = int(sel.index[sel["player_id"] == SIM_CFG["pool"]["target_statsbomb_player_id"]][0])
        left, right = st.columns([1, 3])
        with left:
            label = st.selectbox(f"Player ({SIM_CFG['pool']['min_minutes']}+ minutes)", labels, index=default,
                                 key="player")
            st.markdown("**Group weights** (rescaled to add up to 1)")
            gs = DASH["group_weight_slider"]
            raw = {g["name"]: st.slider(GROUP_LABEL.get(g["name"], g["name"]), gs["min"], gs["max"], float(g["weight"]),
                                        gs["step"], key=f"w_{g['name']}") for g in SIM_CFG["groups"]}
            bs, ag, cons = DASH["budget_slider_eur"], DASH["age_slider"], SIM_CFG["constraints"]
            budget = st.slider("Budget cap (EUR)", bs["min"], bs["max"], int(cons["budget_cap_eur"]), bs["step"],
                               format="%d", key="budget")
            ages = st.slider(f"Age range at {VAL_DATE}", ag["min"], ag["max"], (cons["age_min"], cons["age_max"]),
                             key="age")
        with right:
            row = sel[sel["label"] == label].iloc[0]
            try:
                shares = dash.normalise_weights(raw)
                out = explore(str(PROCESSED), int(row["player_id"]), tuple(sorted(raw.items())), float(budget),
                              tuple(ages))
            except ValueError as e:
                st.warning(f"Cannot compute similarity with these settings: {e}")
            else:
                st.caption("Weights used: " + ", ".join(f"{GROUP_LABEL.get(k, k)} {v:.0%}" for k, v in shares.items())
                           + f". Pool: {out['counts']['pool']} {row['role'].lower()}s with "
                           f"{SIM_CFG['pool']['min_minutes']}+ minutes; {row['club']} players excluded.")
                st.altair_chart(percentile_chart(out["profile"], f"{row['name']}, {SEASON}: percentiles in his role"),
                                width="stretch")
                st.markdown(f"**Most similar players in his role** ({WORDING}; no price or age filter)")
                st.dataframe(out["similar"], hide_index=True, width="stretch", column_config=money(None))
                st.markdown(f"**Value-for-money shortlist** (within EUR {budget / 1e6:g}m, ages {ages[0]}-{ages[1]}; "
                            f"{out['counts']['eligible']} eligible)")
                st.dataframe(out["shortlist"], hide_index=True, width="stretch", column_config=money(None))
                st.caption("The metric groups and their default weights were chosen for the Kanté case "
                           "(config/similarity.yaml); for other roles they are a starting point, not a tuned model. "
                           f"Stale valuation: older than {STALE_DAYS} days at {VAL_DATE} (flagged, kept).")

# ---------- credits ----------
st.divider()
st.caption(PUB["statsbomb_logo"]["source_line"] + " " + PUB["transfermarkt_credit"]
           + f" Summaries only, never event-level data. Every list is a {WORDING}.")
