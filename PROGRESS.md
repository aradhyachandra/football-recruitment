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
