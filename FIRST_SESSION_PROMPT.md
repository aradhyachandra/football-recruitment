Read CLAUDE.md and PROJECT_PLAN.md fully. Do milestone R1 only.

Scope:
- The plan files are already committed. Build the repo skeleton (src/recruit/, sql/, tests/,
  config/, docs/, docs/templates/, results/; data/raw/ and data/processed/ gitignored), a Python venv
  with pinned requirements (duckdb, pandas, pyarrow, PyYAML, pytest; add others only when needed),
  pyproject.toml in the same style as ~/Projects/demand-forecasting.
- config/scope.yaml: season 2015/16 (season_id 27), competitions 2, 11, 12, 7 (Bundesliga 9 excluded:
  only 34 Leverkusen matches), departing player and club (N'Golo Kante, Leicester City), valuation date
  2016-07-01; each with a reason.
- Download from https://raw.githubusercontent.com/hudl/open-data/master/data/ : competitions.json,
  matches for the four competitions, and events and lineups for every listed match, into
  data/raw/statsbomb/. Resumable (skip files already present), polite (small delay), with retries.
  Record total download size and file counts.
- Flatten events one match at a time into parquet under data/processed/ keeping only the fields later
  milestones need (ids, team, player, type, minute/second, location, outcome, pass/carry end
  location, xG, possession, under_pressure and similar); same for lineups including positions with
  from/to times. Record peak memory of the flatten step.
- Download the transfermarkt-datasets snapshot tables players, player_valuations and clubs (from the
  links in its README, or Kaggle) into data/raw/transfermarkt/.
- Record sha256 and row counts of the raw files in config (as in demand-forecasting's raw_files.yaml);
  every run stops if a file changed.
- Load everything into DuckDB with explicit column types.
- Tests first, on small hand-made JSON/CSV fixtures for the flattening and the SQL loading.
- Data audit saved to results/r1_data_report.json and rendered to docs/R1_data_audit.md from a
  template: matches, events and players per league; event type counts; and these GATES:
  (1) valuation records within 6 months of 2016-07-01 for players at clubs in the four leagues
      (count and share; also the departing player's own valuation history around that date),
  (2) Pressure events present in all four leagues,
  (3) lineup positions with from/to times present,
  (4) download size, disk use of parquet, peak memory.
  If a gate fails, stop and report it; do not work around it.

When done, update PROGRESS.md, write docs/R1_data_audit.md in plain language, and list what I should
review. Commit nothing until I say.
