# Football Player Recruitment on a Budget ("Moneyball"): Project Plan

Author: Aradhya Chandra. Status: plan only (no code yet). Target: about 1.5 weeks of build sessions
(R1-R7), finishing before 16 Nov 2026.

## 0. One-paragraph summary

A club loses a key starter. Using free StatsBomb event data for the 2015/16 season (Premier League,
La Liga, Serie A, Ligue 1) and Transfermarkt-derived market values, this project (1) prepares the data
with SQL, (2) builds per-90, possession-adjusted profiles of what each player actually does on the
pitch, by role, (3) finds the players whose profile is most similar to the departing player's,
(4) ranks them on value for money against their market value, and (5) tests how much the shortlist
changes when the assumptions change. The case: **Leicester City lose N'Golo Kante in summer 2016**;
which under-priced players could replace what he contributed (ball-winning and progression, not
goals)? The output is a consulting-style report with a ranked shortlist and a recommendation, a small
local Streamlit dashboard, a README and a case-study page on the portfolio site.

**Principle (same as my other projects):** every number in a document comes from saved results;
every assumption and weight sits in config with a reason; similarity and value results are analysis
under stated assumptions, not proof that a player would succeed.

## 1. The business questions

1. What did the departing player actually contribute, measured per 90 minutes and adjusted for his
   team's possession, compared with others in his role?
2. Which players in the four leagues have the most similar profile?
3. Which of them are under-priced: similar profile, much lower market value, within budget?
4. How stable is the shortlist when the feature weights, minutes threshold or valuation date change?
5. What would we recommend, and what can this analysis not tell us?

## 2. Data (checked 2026-10-29)

**StatsBomb Open Data** (https://github.com/hudl/open-data; the repo moved from statsbomb/open-data
after Hudl acquired StatsBomb). JSON files: competitions, matches, events and lineups per match.
- 2015/16 (season_id 27) coverage counted on 2026-10-29: Premier League (competition 2) 380 matches,
  La Liga (11) 380, Serie A (12) 380, Ligue 1 (7) 377. The 1. Bundesliga (9) has only 34 matches, all
  Bayer Leverkusen games, so it is **excluded** (other clubs' players would have 1-2 matches each).
- Terms (StatsBomb Public Data User Agreement, LICENSE.pdf in the repo, read 2026-10-29):
  analysis and research use; no commercial use; the data may not be distributed or provided to any
  third party; any published analysis must credit StatsBomb with the StatsBomb logo (Media Pack:
  https://statsbomb.com/media-pack/); users are asked to register at
  https://statsbomb.com/resource-centre (done by Aradhya, not by a tool).
- Consequences: raw and processed data are never committed; event-level data never appears in any
  public output; results/ holds only the outputs the docs need (shortlists, rankings, summaries), not
  full per-player feature tables; the StatsBomb logo and source line go on the report, README,
  dashboard and portfolio page.

**Market values: transfermarkt-datasets** (https://github.com/dcaribou/transfermarkt-datasets;
Kaggle mirror https://www.kaggle.com/datasets/davidcariboo/player-scores). Licence: CC0-1.0, as
declared by the maintainer. Tables used: players, player_valuations, clubs (others only if needed).
- Provenance caveat: the dataset is built by scraping Transfermarkt. We do not scrape anything; we use
  the published snapshot for non-commercial portfolio research, and the report states the provenance.
- The dataset was frozen in July 2026 (updates paused upstream). That does not affect 2015/16.
- TO VERIFY in R1 (gate): valuation records exist around mid-2016 for players in the four leagues.
  Not checked yet (the download host was unreachable from the planning environment).
- Values are crowd-sourced estimates, not transfer fees or wages. Market value is the only price
  signal; the report says so.

**Season alignment:** profiles use 2015/16 matches; each player's value is the latest valuation on or
before a configured date (default 2016-07-01, the opening of the summer window). Any player whose
nearest valuation is far from that date is flagged; the allowed gap lives in config.

**Joining the two sources:** there is no shared player ID. Match on normalised name + club + season
(+ birth date or nationality where available), report the match rate, and keep manual fixes for
important players in config with a reason. Unmatched players stay in the similarity step but cannot be
priced; the report gives the count.

## 3. SQL layer (deliberate: shows SQL on real data)

- Raw JSON is downloaded match by match and flattened in Python to compact parquet (only needed
  fields), so memory stays low. DuckDB then does the preparation in SQL files under `sql/`, run by
  Python: minutes played (from lineup positions and substitutions), per-match team possession,
  player-season totals by action type, role assignment, joins to market values.
- Tests compare SQL outputs with small hand-made tables.

## 4. Analysis design

- **Unit:** player-season (2015/16), one league per player (players who moved mid-season: handled by
  a rule in config, decided in R2).
- **Minutes threshold:** minimum league minutes for a stable profile (default 900; reason and
  sensitivity in config).
- **Roles:** from the StatsBomb positions a player played most minutes in, grouped into role buckets
  (mapping in config). The comparison pool is the departing player's role.
- **Metrics (draft, finalised in R2):** per 90 minutes: tackles won, interceptions, ball recoveries,
  pressures and pressure regains, blocks, fouls committed, passes completed, progressive passes,
  passes into the final third, progressive carries, successful dribbles, shots, xG, key passes.
  Exact event definitions (for example "progressive") live in config with a reason.
- **Possession adjustment:** defensive actions scaled to a common possession level using the team's
  possession share in the matches the player played (formula in config). Possession is estimated from
  StatsBomb possession sequences; method decided and tested in R2.
- **Similarity:** standardise metrics within the role pool (z-scores), apply feature weights (config,
  each with a reason), cosine similarity to the departing player. A split-half check (first vs second
  half of the season) measures how often a player's nearest neighbour is himself, as an honest test of
  whether the profiles are stable enough to compare.
- **Value for money:** two views. (a) Weight-free: the frontier of players for whom no one else is both
  more similar and cheaper. (b) Weighted score combining similarity and price, with weights in config.
  Constraints in config: budget cap, age range at the valuation date, exclude the departing player's
  own club.
- **Sensitivity:** perturb feature weights (fixed seed), change the minutes threshold, valuation date
  and score weights; report how often each player stays in the top N and his rank range.
- **No hindsight:** the analysis uses only 2015/16 match data and valuations up to the configured date.
  Later careers are not used to choose or tune anything; the report notes that the case is historical.
- **Wording rule:** "similar profile under stated assumptions", never "would succeed" or "proven".

## 5. Deliverables

1. Findings report (consulting style, ~8-10 pages): situation, what the departing player contributed,
   method, similar players, value-for-money shortlist and recommendation, sensitivity, limits. All
   numbers generated from saved results; StatsBomb logo and data credits.
2. Streamlit dashboard, run locally: pick a player, see his profile vs the role, the most similar
   players and their values, with weight sliders. Reads only results/ and data/processed/. README shows
   screenshots/GIF; not deployed (StatsBomb no-redistribution clause).
3. Repo: README with the shortlist, how to reproduce (download instructions), data terms, limits.
4. Case-study page on aradhyachandra.github.io (built from ~/Projects/portfolio-site).

## 6. Milestones (about one Claude Code session each; tests first)

| ID | What | Done when |
|---|---|---|
| R1 | Repo setup; download StatsBomb 2015/16 (4 leagues) and the Transfermarkt snapshot; flatten events to parquet; load into DuckDB; data audit | Raw files fingerprinted; match/event/player counts saved; gates checked: valuations around mid-2016, pressure events present, lineup positions present, download size and peak memory recorded |
| R2 | Player-season profiles in SQL: minutes, per-90 metrics, possession adjustment, roles, thresholds | SQL tested on hand-made tables; profile summary saved; departing player's profile vs his role saved |
| R3 | Join to market values: name matching, valuation as of the configured date | Match rate saved overall and by league/role; manual fixes in config; unmatched list saved |
| R4 | Similarity, split-half stability check, value-for-money frontier and score, shortlist | Similarity and shortlist saved; stability result saved; tests on hand-made profiles |
| R5 | Sensitivity analysis and findings report | Top-N frequency and rank ranges saved; docs/REPORT.md rendered from results |
| R6 | Streamlit dashboard and README | Dashboard runs locally and is tested; README rendered from results; screenshots saved |
| R7 | Portfolio case-study page; clean-clone check | Page added to portfolio-site; clean clone reproduces results |

## 7. Working rules for any coding tool

- Read this plan and PROGRESS.md first; one milestone per session, in order; tests first.
- All assumptions, thresholds, weights and mappings live in `config/` with a one-line reason.
- No invented numbers: doc figures come from saved results (templates in docs/templates/).
- 8 GB RAM: flatten one match at a time, keep only needed columns, prefer DuckDB/parquet, never load
  all events into pandas at once.
- Data terms: never commit data/raw/ or data/processed/; nothing event-level in public outputs;
  StatsBomb logo and source credit on every published analysis.
- Mark uncertain things TO VERIFY in NOTES.md; end each session updating PROGRESS.md and a short
  plain-language note in docs/.

## 8. Risks

- Valuation history too thin around 2016 (R1 gate): fall back to the nearest available valuation with
  the gap stated, or narrow the pool to players with a valuation within the allowed gap.
- Low name-match rate between sources: report it; manual fixes for important players.
- Small samples: minutes threshold plus the split-half check; flag players near the threshold.
- Possession adjustment and event definitions are modelling choices: tested, documented, and covered
  by the sensitivity analysis.
- Hindsight bias: the case is historical; the report says so and no later information is used.
- Data size: several GB of JSON; streaming and parquet keep memory low; raw files stay out of git.

## 9. README outline

What and why · The case · Shortlist and recommendation · How it works (diagram) · Sensitivity ·
Reproduce (download instructions) · Data, terms and credits (StatsBomb logo) · Assumptions ·
Limitations · Author.
