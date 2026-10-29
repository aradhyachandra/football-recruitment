# Notes and open questions

Items marked **TO VERIFY** need a human decision or check. Resolved items move to "Resolved" with the
date and how they were settled.

## TO VERIFY

- **StatsBomb logo.** The terms require the StatsBomb logo on every published analysis. The R1 and R2
  pages carry a text credit only; Aradhya will fetch the logo from the Media Pack
  (https://statsbomb.com/media-pack/) before anything goes public on GitHub (not before R6).
- **R3 override that rests on outside knowledge.** StatsBomb id 42946 "Jiang Guangtai" (Everton, 5
  matches) is matched to Transfermarkt 156934 "Tyias Browning": same squad, Chinese citizenship, born in
  England, 5 v 5 appearances. That he later took the Chinese name is general knowledge, not in either
  dataset. Low stakes (328 minutes, full back), but worth a glance.
- **Transfermarkt appearances have holes (R3 finding).** Markel Susaeta (Athletic, 1,985 minutes) has
  no Transfermarkt appearances from May 2015 to August 2016, and Rushian Hepburn-Murphy (Aston Villa, 6
  minutes) none before November 2019, so neither is in the squads built from appearances; both are
  matched by override (`outside_squad`). Susaeta is the only plausibility flag (28 StatsBomb matches v 0
  Transfermarkt league appearances). Other players with such a hole would show up the same way; none
  else did.
- **One-word Transfermarkt names (R3).** 16 matches rest on a one-word Transfermarkt name contained in
  the StatsBomb legal name (e.g. "Miranda", "Hernanes", "Jordan" for StatsBomb "Jordan Siebatcheu";
  Transfermarkt's "Jordan" is born 1996-04-26 and plays for Reims); 8 of them reach 900 minutes. All have plausible appearance counts. Worth a skim in
  `data/processed/r3/r3_player_values.parquet` (method token_subset, score 0.88).
- **Stale and missing valuations (R3).** At 900 minutes every matched player has a valuation on or
  before 2016-07-01; 6 are older than 183 days (oldest 391 days; 1 in the Central midfielder pool,
  Zdravko Kuzmanović, 196 days). Below 900 minutes, 56 matched players have no valuation before the date.
  R4 should decide whether stale prices enter the value score or only carry a flag.
- **Unmatched (R3).** Assane Gnoukouri (Inter, 62 minutes) is not in transfermarkt-datasets under any
  spelling found; left unmatched.
- **Glitched timestamps (R2 finding).** 252 events (almost all Premier League and La Liga; mostly the
  last Ball Receipt before Half End) have a timestamp of about 0:00 although they sit at the end of the
  half in StatsBomb's event order. Before the fix, possession-method agreement was correlation 0.74,
  mean difference 5.1 points (PL and La Liga about 8.6 points, Serie A and Ligue 1 about 1.6; from an
  exploratory run before the fix, not saved in results/). After
  leaving them out of timing (`profiles.yaml` event_timestamps, 60 s backward line; no backward step
  in the data falls between 5 s and 300 s) it is 0.98 and 1.7 points in every league. The events still
  count for their metrics. Worth a look that this rule reads as sensible.
- **Twelve players listed (R2 finding).** 25 team-matches have more than 11 x match length in lineup
  minutes (1,227 extra minutes, 0.04% of all). In the largest case, checked by hand, a player coming back
  after "Player Off" and his replacement both stay on to the final whistle. Every "Player On" return
  spell in the data has events by that player in it, so no safe automatic fix was found; spells are
  kept as recorded. A few players may have a few minutes too many.
- **Possession adjustment form.** Linear (`raw x 0.5 / opponent share`, per match). StatsBomb's own
  PAdj uses a sigmoid; its exact constants were not checked here. Candidate for the R5 sensitivity.
  The adjustment factor runs from 0.63 to 2.49 across team-matches.
- **Events without a lineup spell.** 10 player events (of 5,301,066) belong to a player with no lineup
  spell in that match; they count towards no player-match row. Too few to matter, not investigated.
- **Network during download.** DNS dropped out three times during the R1 download; the downloader's
  retries (about 30 s in total) were too short, so it was simply re-run (it resumes). A clean-clone
  check in R7 should expect the same.

## Resolved

- 2026-10-29 (R2): The 80% valuation gate line is kept (Aradhya, after R1; 95.3% passed). Reason in
  config/audit.yaml.
- 2026-10-29 (R2): Transfermarkt `appearances` table accepted as a useful addition (Aradhya): it keeps
  the valuation check independent of the valuations.
- 2026-10-29 (R2): Mid-season movers: one row per player for the season, summed over all clubs and
  leagues in scope, teams and minutes per team kept, possession adjusted per match before summing
  (Aradhya; config/profiles.yaml `unit`). 103 players moved (38 between leagues); 77 reach 900 minutes.
- 2026-10-29 (R2): Players are identified by StatsBomb player_id everywhere; Kanté's id 3961 is in
  config/scope.yaml.

- 2026-10-29: All four R1 gates passed (results/r1_data_report.json, docs/R1_data_audit.md).

- 2026-10-29: Kanté's transfermarkt-datasets player_id is 225083 (the only "N'Golo Kanté" in players,
  born 1991-03-29); recorded in config/scope.yaml.
- 2026-10-29 (after R2): Defensive and centre midfield stay pooled as one "Central midfielder" role
  (Aradhya). Reason: StatsBomb labels follow the formation (Kanté has 1,407 minutes under Defensive
  Midfield labels and 1,723 under Center Midfield labels at the same club); style differences inside
  the pool are left to R4. Reason in config/roles.yaml.
- 2026-10-29 (R3): Apostrophes in names (doubled "N''Golo", typographic, and one double quote) are
  removed before matching (config/matching.yaml normalise); Kanté matches 225083 exactly.
