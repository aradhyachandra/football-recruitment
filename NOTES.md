# Notes and open questions

Items marked **TO VERIFY** need a human decision or check. Resolved items move to "Resolved" with the
date and how they were settled.

## TO VERIFY

- **Valuation gate line (R1).** `config/audit.yaml` sets the pass line at 80% of league players having
  a valuation in the 6 months before 2016-07-01. That number is my proposal, not from the plan; please
  confirm or change it.
- **StatsBomb logo.** The terms require the StatsBomb logo on every published analysis. The R1 audit
  page carries a text credit only; the logo file must be fetched by Aradhya from the Media Pack
  (https://statsbomb.com/media-pack/) and added to docs/ before anything is published.
- **Transfermarkt `appearances` table.** Added beyond the plan's three tables, so the valuation gate
  has an independent list of who played in the four leagues in 2015/16 (reason in config/data.yaml).
- **Mid-season movers.** The valuation gate counts a player once overall but once per league in the
  by-league rows, so league rows can add up to more than the total. The R2 rule for players who moved
  mid-season is still open (plan Section 4).
- **Departing player's StatsBomb id.** The R1 audit finds one id, 3961 (Leicester City, 37 matches), but
  under two spellings: "N''Golo Kanté" (doubled apostrophe, 36 matches) and "N'Golo Kanté" (1 match).
  R2 should put `statsbomb_player_id: 3961` in config/scope.yaml and use ids, not names. R3 name
  matching must normalise apostrophes; other names may have the same quirk.
- **Network during download.** DNS dropped out three times during the R1 download; the downloader's
  retries (about 30 s in total) were too short, so it was simply re-run (it resumes). A clean-clone
  check in R7 should expect the same.

## Resolved

- 2026-10-29: All four R1 gates passed (results/r1_data_report.json, docs/R1_data_audit.md).

- 2026-10-29: Kanté's transfermarkt-datasets player_id is 225083 (the only "N'Golo Kanté" in players,
  born 1991-03-29); recorded in config/scope.yaml.
