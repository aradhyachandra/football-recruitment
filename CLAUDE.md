# Instructions for coding tools

Read PROJECT_PLAN.md fully, then PROGRESS.md (create it if missing). One milestone per session, in
order (Section 6). Tests first, on small hand-made data. Keep code readable.

Hard rules:
- No invented figures; every number in docs/report/README comes from saved results.
- Every assumption, threshold, weight and mapping lives in config/ with a reason; never hard-code them.
- Never commit data/raw/, data/processed/ or any secret. Pin dependencies in requirements.txt.
- StatsBomb terms: no event-level data in any public output; results/ keeps only what the docs need
  (shortlists, rankings, summaries); credit StatsBomb with its logo on every published analysis.
- Do not scrape any website. Use only the published StatsBomb and transfermarkt-datasets files.
- 8 GB RAM laptop: process one match at a time, keep only needed columns, use DuckDB and parquet.
- No hindsight: use only 2015/16 match data and valuations up to the configured date.
- Wording: similarity and value results are analysis under stated assumptions, not proof a player
  would succeed.
- Mark uncertain things TO VERIFY in NOTES.md. End of session: update PROGRESS.md and add a short
  plain-language note in docs/. Commit nothing unless asked.
