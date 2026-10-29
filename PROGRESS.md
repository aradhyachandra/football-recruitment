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

Next: R2, player-season profiles in SQL (minutes from lineup stints, per-90 metrics, possession
adjustment, roles, thresholds). First set `statsbomb_player_id: 3961` for Kanté in scope.yaml.
