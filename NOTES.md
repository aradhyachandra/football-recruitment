# Notes and open questions

Items marked **TO VERIFY** need a human decision or check. Resolved items move to "Resolved" with the
date and how they were settled.

## TO VERIFY

- **StatsBomb logo.** The terms require the StatsBomb logo on every published analysis. The R1 and R2
  pages carry a text credit only; Aradhya will fetch the logo from the Media Pack
  (https://statsbomb.com/media-pack/) before anything goes public on GitHub (not before R6).
- **Transfermarkt appearances have holes (R3 finding).** Markel Susaeta (Athletic, 1,985 minutes) has
  no Transfermarkt appearances from May 2015 to August 2016, and Rushian Hepburn-Murphy (Aston Villa, 6
  minutes) none before November 2019, so neither is in the squads built from appearances; both are
  matched by override (`outside_squad`). Susaeta is the only plausibility flag (28 StatsBomb matches v 0
  Transfermarkt league appearances). Other players with such a hole would show up the same way; none
  else did.
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

- **R4: half the shortlist has no split-half rank.** 5 of the 10 shortlisted players (and 59 of the
  307 pool players) have under 450 minutes in one half of the season, so the stability check could
  not rate them; their full-season profiles rest on 1,121-1,547 minutes. Worth weighing when reading
  the shortlist (docs/R4_shortlist.md).
- **R4: value score leans towards cheap players.** Percentile cheapness among the 134 eligible
  players, many valued at EUR 1-2.5m, lets players ranked 41st and 43rd by similarity into the
  shortlist (ranks 7 and 6). This is the configured 0.7/0.3 weighting acting as written, not changed
  after seeing names; R5 should test other score weights. The frontier gives the weight-free view.
- **R4: similarity scores sit in a narrow band.** The fixed 0-100 scale (100 * (1 - d / 6)) puts the
  top 10 between 84.6 and 90.2, so small score gaps look larger in ranks than they are. Ranks follow
  the distance either way; the split-half check suggests gaps of a point or two are within noise.
- **R4: frontier includes players outside the constraints.** 4 of the 10 frontier players are 32-39
  (the frontier is computed before constraints, by design, and flags them). One (Enzo Maresca) has a
  valuation dated exactly 2016-07-01, allowed by the "on or before" rule.

## Resolved

- 2026-10-29 (R4): StatsBomb id 42946 "Jiang Guangtai" = Transfermarkt 156934 "Tyias Browning":
  confirmed by Aradhya; he took the name on naturalisation in China in 2019. Override kept.
- 2026-10-29 (R4): The 16 one-word-name matches (method token_subset) were reviewed by hand by
  Aradhya: all correct.
- 2026-10-29 (R4): Stale valuations (older than 183 days) stay in the ranking with a visible flag in
  every output; R5 tests dropping them (Aradhya; config/similarity.yaml constraints.stale_valuations).
  In the Central midfielder pool 1 priced candidate is stale; none is on the shortlist.
- 2026-10-29 (R4): Primary similarity is a weighted Euclidean distance on standardised metrics (0-100
  score), with cosine reported as a shape check (Aradhya). Reason: level matters for a replacement.
  PROJECT_PLAN.md section 4 updated.

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
