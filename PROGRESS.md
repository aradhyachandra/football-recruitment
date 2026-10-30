# Progress

One milestone per session, in the order of PROJECT_PLAN.md Section 6.

## R1: repo setup, download, flatten, DuckDB, data audit (2026-10-29): done, nothing committed

Built:
- `src/recruit/`: `download.py` (resumable, polite, retries), `flatten.py` (JSON to parquet, one match
  at a time, fields from `config/statsbomb_fields.yaml`), `raw_files.py` (sha256 fingerprints and
  row/record counts in `config/raw_files.yaml`; every run stops on a change), `load.py` (DuckDB,
  explicit types), `audit.py` (counts and the four gates, SQL in `sql/r1_*.sql`), `report.py`
  (template filling), `run_r1.py` (whole step).
- Config: `scope.yaml` (season, leagues, departing player and ids, valuation date, season window),
  `data.yaml`, `statsbomb_fields.yaml`, `audit.yaml` (gate lines), `raw_files.yaml` (generated).
- Outputs: `results/r1_data_report.json`, `docs/R1_data_audit.md` (from `docs/templates/`).
- Tests: 30, all passing, on hand-made fixtures in `tests/fixtures/`.

Gates: all four PASS. The figures are in docs/R1_data_audit.md.

Reproduce:
    .venv/bin/python -m recruit.download
    .venv/bin/python -m recruit.run_r1          # (--record was used once to write raw_files.yaml)

Open points: see NOTES.md (TO VERIFY).

## R2: player-season profiles in SQL (2026-10-29): done, nothing committed

Built:
- SQL (`sql/r2_*.sql`), run in order by `src/recruit/profiles.py`: `r2_events` (event columns, time in
  seconds, derived flags, bad-timestamp flag), `r2_period_lengths`, `r2_stints` (minutes per lineup
  spell, role), `r2_team_possession` (in-play share; pass share as a check), `r2_player_match`
  (raw and possession-adjusted values per match), `r2_player_season` (one row per player, per 90).
  Summary queries: `r2_pool_sizes`, `r2_distributions`, `r2_departing_profile`, `r2_possession_check`,
  `r2_team_minutes`, `r2_checks`.
- Config: `profiles.yaml` (match clock, possession method, adjustment formula, timestamp rule, minutes
  threshold 900 and 600/900/1,200 sensitivity, unit rule for movers), `metrics.yaml` (16 metrics + pass
  completion; every event definition with a reason; none dropped), `roles.yaml` (7 role buckets).
  `scope.yaml` now holds Kanté's StatsBomb id 3961; `audit.yaml` records the confirmed 80% line.
- `src/recruit/run_r2.py`: builds in the R1 DuckDB, writes `data/processed/r2/*.parquet` (gitignored),
  `results/r2_profiles_summary.json` (summaries only) and `docs/R2_profiles.md` (from the template).
- Tests: 28 new (58 in all), on hand-made tables in `tests/r2_data.py` (subs, red card, half-time sub,
  position change, temporary player-off, clock past period end, mid-season mover, glitched timestamp).

Key numbers are in docs/R2_profiles.md. Data finding: 252 events carry a timestamp of about 0:00 at the
end of a half; left in, they broke the possession share in 132 Premier League and 125 La Liga
matches. A config rule now leaves them out of timing (details in NOTES.md and profiles.yaml).

Reproduce (after R1):
    .venv/bin/python -m recruit.run_r2      # about 10 s; peak memory about 2 GB (DuckDB limit)

Next: R3, join to market values (name matching via StatsBomb player_id -> transfermarkt player_id,
valuation as of 2016-07-01). Apostrophes in names need normalising (see NOTES.md).

## R3: join to market values (2026-10-29): done, nothing committed

Built:
- Club map first: `config/club_map.yaml`, 80 StatsBomb teams -> 80 Transfermarkt clubs, reasons for the
  non-obvious names. Checked on every run against fixture dates (`sql/r3_club_dates.sql`): every
  StatsBomb league match date has a league appearance for the mapped club; all 80 teams at 100%.
- Name matching inside club squads (`src/recruit/matching.py`, stdlib difflib, no new dependency):
  normalisation (accents, apostrophes incl. the doubled one and a double quote, hyphens, đ -> dj),
  methods exact_name / exact_nickname / token_subset / token_prefix / fuzzy, score per match,
  ambiguity margin with country as tie-breaker, one Transfermarkt player per StatsBomb player.
  Manual fixes: `config/player_overrides.yaml` (8, each with reason and evidence; 2 marked
  outside_squad because Transfermarkt's appearances table misses them for 2015/16).
- SQL (`sql/r3_*.sql`, run by `src/recruit/market_values.py`): squads from appearances in the season
  window, StatsBomb name spellings, plausibility (StatsBomb matches vs Transfermarkt league apps per
  club), joined table with latest valuation on or before 2016-07-01, gap in days, stale flag (183 days),
  age at the date.
- Config: `config/matching.yaml` (every threshold with a reason), `club_map.yaml`, `player_overrides.yaml`.
- `src/recruit/run_r3.py`: writes `data/processed/r3/*.parquet` (gitignored),
  `results/r3_join_summary.json` (summaries, Kanté's record, 30-pair seeded sample, unmatched list
  with name/team/role) and `docs/R3_market_values.md` (from the template). `report.py` gained a
  two-decimal percentage format so 2,175/2,176 does not print as 100.0%.
- Tests: 47 new (105 in all), on hand-made data in `tests/r3_data.py` (doubled apostrophe, accents,
  hyphen, full legal vs short name, similar names at one club, ambiguous pair, mid-season mover at both
  clubs, valuation after the date ignored, stale valuation kept, override typo guard, club map checks).

Key numbers are in docs/R3_market_values.md. Kanté -> Transfermarkt 225083 (checked against
config/scope.yaml on every run).

Reproduce (after R1 and R2):
    .venv/bin/python -m recruit.run_r3      # about 17 s

Next: R4, similarity, split-half stability, value-for-money frontier and score, shortlist. R4 must
decide how to treat stale valuations (6 players at 900 minutes, 1 in the Central midfielder pool).

## R4: similarity, stability, value for money, shortlist (2026-10-29): done, nothing committed

Config first: `config/similarity.yaml` (pool, metric groups and weights with reasons tied to Kanté's
R2 percentiles, possession-adjusted defensive metrics, z-scores clipped at +/-3, distance-to-score
rule, cosine check, split-half settings, frontier rule, value-score weights, constraints, stale and
unpriced rules) was written and fingerprinted before any run on real data:
    554dedea75d9565502e14ffa3e24c30e4bb612d89ee7b87b2df7adb4887fd77b
Unchanged through every run (no weight was changed after seeing names); the hash is saved in
results/r4_shortlist.json and checked against this line by eye.

Built:
- `src/recruit/similarity.py`: pure maths (metric weights, profile matrix, standardise and clip,
  weighted Euclidean distance, 0-100 score, cosine, group gaps, percent_rank, split-half self-match
  ranks, weak-dominance frontier, constraints, value score and ranking).
- `sql/r4_half_profiles.sql`: per-player half-season per-90 values (split at 2016-01-01), same
  arithmetic as r2_player_season; the run checks half minutes add up to season minutes.
- `src/recruit/run_r4.py`: `analyse()` (pure, tested on hand-made data), writes
  `data/processed/r4/r4_similarity.parquet` (every pool player, gitignored),
  `results/r4_shortlist.json` (shortlist, top-similar, frontier, target, stability, config sha256),
  `docs/R4_shortlist.md` (from `docs/templates/R4_shortlist.md`).
- `src/recruit/r4_figures.py`: `docs/figures/r4_similarity_vs_value.png` (frontier and shortlist
  numbered with a key, others unlabelled) and `docs/figures/r4_profile_comparison.png` (Kanté vs top
  3 of the shortlist, pool percentiles); both carry the StatsBomb source credit as text.
- `requirements.txt`: matplotlib==3.10.7 added (figures).
- PROJECT_PLAN.md section 4: Euclidean distance as primary similarity, cosine as a check (reason given).
- Tests: 31 new (136 in all), hand-made profiles in `tests/test_similarity.py` and `tests/test_run_r4.py`.

Key numbers are in docs/R4_shortlist.md (pool 307; 134 candidates meet the constraints; split-half:
own profile closest for 21.0% and in the top 5 for 48.8% of 248 players, Kanté 11th).

Reproduce (after R1-R3):
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python -m recruit.run_r4      # about 2 s

Next: R5, sensitivity (weights perturbed with a fixed seed, minutes threshold, valuation date,
value-score weights, dropping stale valuations, raw vs adjusted defensive metrics) and the report.
Open R4 points in NOTES.md.

## R5: sensitivity analysis and findings report (2026-10-29): done, nothing committed

Config first: `config/sensitivity.yaml` (16 named one-change scenarios including the base, 300 Dirichlet
weight draws, robust-core line, recommendation rule) was written and fingerprinted before any run on
real data:
    4cea2681f7e3cf717b10a3337a5cccb1e2baa6160232f8c665d9a69844292172   (before any run)
One change after the first real-data run, reporting only: `outputs.draw_rank_quantiles: [0.05, 0.95]`
(with reason) moved the rank band shown for the random draws out of the code into config. Scenarios,
core line and recommendation rule unchanged; robust core and recommendation identical before and after.
    376748f06bb6b302e7e7ed0e152c86ce9f6d5c16ecfc7508dc273d462e7ae1b5   (current, saved in results)
`config/similarity.yaml` unchanged (554dedea...); the run stops if it differs from R4's, and the base
scenario must reproduce the R4 shortlist exactly (it does).

Built:
- `src/recruit/sensitivity.py`: one-change configs (dotted paths, `group_weights`; unknown keys raise),
  config fingerprint per scenario, seeded Dirichlet group weights, the runner, robustness counts
  (top-10 / top-3 shares, median rank, min-max and quantile band), robust core, recommendation rule
  with fallback, summary.
- R4 code extended without changing R4 results (checked: rerun gives an identical r4_shortlist.json
  apart from run time): value-score scales `minmax_log_value_across_pool` and `similarity_only`
  (`run_r4.value_scores`, `similarity.value_score_minmax_log`), stale rule `exclude`, `with_stability` flag.
- `src/recruit/run_r5.py`, `src/recruit/r5_figures.py` (docs/figures/r5_top10_by_scenario.png,
  r5_rank_ranges.png; StatsBomb source text on both), `src/recruit/report_r5.py` (derived figures saved
  as `report_facts` in results/r5_sensitivity.json, tables, rendering). `report.py`: `ord` and `plain` formats.
- Outputs: `results/r5_sensitivity.json` (summaries only: per-scenario top lists and fingerprints,
  34 saved candidates with robustness, core, recommendation), `docs/R5_sensitivity.md` (short plain note),
  `docs/REPORT.md` (findings report, about 4,700 words with tables) from `docs/templates/`.
- Tests: 26 new (162 in all): scenario runner, Dirichlet reproducibility and centring, robustness counts,
  core and recommendation (incl. tie-break and fallback), new value scores and stale rule, wording rules,
  "every number in the report is in results/" (and the report template holds no literal figures).

Results (docs/REPORT.md): robust core of 7 (value top 10 in at least 12 of 16 scenarios);
recommendation Sebastián Cristóforo, backups Jessy Pi and Benjamin André, all in the core.

Reproduce (after R1-R4):
    .venv/bin/python -m recruit.run_r5      # about 7 s, peak memory about 0.3 GB

Next: R6, Streamlit dashboard and README (StatsBomb logo still TO VERIFY).

## R6: publication fixes, dashboard and README (2026-10-29): done, nothing committed or pushed

Decisions recorded in NOTES.md (Resolved): the report keeps the pre-set recommendation with the two-route
framing; the recommendation rule is unchanged.

Publication fixes:
- Hindsight trim: `sql/r1_departing_valuations.sql` and `sql/r1_valuation_gate.sql` read nothing after the
  valuation date (history = 12 months up to it; the "either side" counts are gone), `audit.py`,
  `config/audit.yaml`, the R1 template. `run_r1.py --audit-only` re-runs the audit on the existing DuckDB
  (fingerprints verified, no download, later milestones' tables kept; size and memory figures carried
  over from the last full run). `src/recruit/hindsight.py` + `tests/test_hindsight.py`: no date after the
  valuation date and no negative days-before in any results/*.json (run fields exempt). Before the fix
  it flagged only the R1 history (3 dates, 3 negative day counts).
- Season label: `config/scope.yaml` season.label, `config.season_label()`, `report.publication_context()`
  (label + logo tag) in every renderer; templates use `{{season_label}}` and `{{logo_html}}`; figure credit
  and title read the label. R1 (audit-only) and R2-R5 re-run: R3-R5 results identical apart from run
  fields, R1 changed only by the trim, R2 differs only at the 15th-16th digit (committed file kept; see
  NOTES.md); figures byte-identical.
- Logo: `assets/statsbomb_logo.png` from the Media Pack (redirects to hudl.bynder.com; file, sha256 and
  terms in `config/publication.yaml` and NOTES.md); on REPORT.md, every step note, README and dashboard.

Dashboard:
- `src/recruit/dashboard.py` (pure: loads results/ and data/processed/ parquet, builds the Explore config
  with `sensitivity.apply_changes` and runs `run_r4.analyse`; display tables). `app/streamlit_app.py`
  (Case and Explore tabs, logo, credits, wording). `.streamlit/config.toml` (light theme for the logo).
  Settings and slider ranges in `config/publication.yaml` (dashboard).
- Screenshots: `docs/figures/r6_dashboard_case.png`, `r6_dashboard_explore.png`, taken with the local
  Google Chrome in headless mode driven over the DevTools protocol (script kept outside the repo; uses the
  `websockets` package streamlit already installs; nothing added to requirements.txt).
- `requirements.txt`: streamlit==1.66.0, altair==6.3.0 (other pins unchanged).

README: `docs/templates/README.md` -> `README.md` by `src/recruit/run_r6.py` (reuses the R5 report
context and tables; README-only figures saved to `results/r6_readme.json`). `LICENSE` (MIT, code only;
data and logo not covered, not included).

Tests: 31 new (193 in all, all passing): hindsight scanner and results check, audit-only mode, logo
checksum and doc placeholders, commit-safety (nothing from data/, no event-level fields in results/),
dashboard pure functions on hand-made data, Kanté defaults reproduce the R4 lists exactly (real data),
AppTest smoke test without data/processed and with it (sliders), README up to date, every README number in
results/, LICENSE.

Reproduce (after R1-R5):
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python -m recruit.run_r1 --audit-only   # only if the R1 audit/template changes
    .venv/bin/python -m recruit.run_r6                # README, under a second
    .venv/bin/streamlit run app/streamlit_app.py

Next: R7, portfolio case-study page and clean-clone check (compare R2 with a tolerance; see NOTES.md).
