# Notes and open questions

Items marked **TO VERIFY** need a human decision or check. Resolved items move to "Resolved" with the
date and how they were settled.

## TO VERIFY

- **StatsBomb logo.** The terms require the StatsBomb logo on every published analysis. The R1 and R2
  pages carry a text credit only; Aradhya will fetch the logo from the Media Pack
  (https://statsbomb.com/media-pack/) before anything goes public on GitHub (not before R6).
- **R3 name matching.** StatsBomb names can carry a doubled apostrophe ("N''Golo Kanté" for id 3961);
  R3 matching must normalise apostrophes, and other names may have the same quirk. R2 uses ids only.
- **Role pooling (R2).** `config/roles.yaml` pools defensive midfield (StatsBomb 9-11) and centre
  midfield (13-15) into one "Central midfielder" role, because the label follows the team's formation:
  Kanté has 1,407 minutes as Left/Right Defensive Midfield and 1,723 as Right/Left Center Midfield for
  the same club. The pool has 307 players at 900 minutes. Please confirm, or ask for a split (R4 could
  also weight style differences within the pool).
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
