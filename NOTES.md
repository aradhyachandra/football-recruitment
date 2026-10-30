# Notes and open questions

Items marked **TO VERIFY** need a human decision or check. Resolved items move to "Resolved" with the
date and how they were settled.

## TO VERIFY

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

- **R5: the recommendation leans on price.** Sebastián Cristóforo is in the value top 10 in every named
  scenario and top 3 in 81.2%, but 13th by similarity alone (similarity top 10 in 12.5% of the
  similarity scenarios), not rated by the split-half check, and his 1,503 minutes are 3 above the
  highest threshold tested. The most similar eligible profiles (Jack Cork, Nemanja Radoja) win when
  price is dropped or log-scaled. The rule was fixed in advance; worth a human view on whether the
  club's question is "closest we can afford" or "most profile per euro" (docs/REPORT.md).
- **R5: config amended once after the first run** (reporting only): `outputs.draw_rank_quantiles` in
  config/sensitivity.yaml; fingerprints before/after in PROGRESS.md. Results unchanged.

- **R6: logo terms are thin.** statsbomb.com/media-pack now redirects to Hudl's brand portal
  (hudl.bynder.com, collection "Hudl Statsbomb Logos"). The file used is "hudl-statsbomb-logo-default"
  (PNG original, unchanged; sha256 in config/publication.yaml). The only usage statement found is the
  asset's metadata "Usage Rights: External Use Approved"; no written logo guidelines (clear space,
  minimum size, which variant on which background) were found on the portal. The logo now reads
  "Hudl StatsBomb", not the older "StatsBomb" mark. Worth a look before publishing, and worth an email
  to StatsBomb/Hudl if the portfolio page needs certainty.
- **R6: R2 reruns differ in the last digits.** Rerunning R2 gives per-90 distributions that differ at
  the 15th-16th significant digit (DuckDB parallel float sums; up to about 1e-15 relative). Rendered docs
  and every later result are identical. The committed results/r2_profiles_summary.json was kept (the
  rerun copy was not saved). The R7 clean-clone check should compare R2 with a tolerance, or R2 could
  run single-threaded if bit-for-bit reruns matter.
- **R6: README run times come from two sessions.** R2's time is from the committed R2 run; R3-R5's from
  this session's re-render runs (results/ run fields). R1's load-and-audit step and the download have no
  saved time, and the README says so.
- **R6: the valuation date was not varied in R5.** PROJECT_PLAN.md section 4 lists it among the
  sensitivity changes; R5's scenarios do not include it (the README assumptions table says "not varied").
  An earlier date would only ever use older valuations (no hindsight), so it could be added in R7 if
  wanted.
- **R6: the Case-view screenshot shows the whole pool as dots.** It plots similarity against market value
  for every priced central midfielder (unlabelled, hover only in the live app), like the R4 figure.
  These are derived per-player summaries, not event data; worth a glance against the "no per-player full
  tables" rule before publishing.
- **R6: Explore view uses the Kante weights for every role.** Group weights and metrics were chosen for
  the Kante case; for other roles the app says they are a starting point. The selected player's own
  club(s) are excluded as targets (config/publication.yaml), which for Kante is exactly the R4 rule.

- **R7: the portfolio page goes live before the repo exists.** The page links to
  github.com/aradhyachandra/football-recruitment and its docs/REPORT.md, which do not exist until the repo is
  created and pushed. Push the project first, then the site.
- **R7: site copy changed outside the football page.** The home page results strip header now reads "Tested on
  data the models never saw, or across stated scenarios", the Projects heading "Four business questions" and
  the lede "...on data it never saw or across stated scenarios", because the football result is a scenario
  test, not a held-out test. The strip is now 2 columns from 720px and 4 from 1100px. Worth a look.
- **R7: case-study gutter fix touches every case study.** `.cs-layout { padding: ... 0 ... }` removed the
  `.wrap` side padding, so on phones the body text of every case study touched the screen edge (and on desktop
  the contents sat a gutter left of the hero). Now top/bottom padding only. The older phone-churn, phone-demand
  and phone-tcs screenshots (16 Oct) predate the 26 Oct redesign and were not re-taken.
- **R7: home-page screenshots are now full page.** desktop-home-*.png used to be the top 3000 px; the new ones
  (and the new football ones) are the full page, at the same widths (1366 px; phones 375 px at 2x).
- **R7: Radoja's similarity prints as 89.5 in the R4 figure and 89.6 in the dashboard.** results/ stores 89.55
  (two decimals); the figure formats that stored value with one decimal (binary float rounds down), the dashboard
  rounds the unrounded value. The site does not print his score. A one-line fix in r4_figures.py would change a
  committed figure, so it was left for a decision.
- **R7: clean clone ran on committed R6 code.** R7's own code (dashboard polish, the check itself) was not in
  the clone because nothing is committed. Re-running `recruit.clean_clone` after the R7 commit would cover it
  (about 4-5 minutes).
- **R7: the README does not mention R7 yet.** It is generated (docs/templates/README.md); adding a line on the
  clean-clone check was left out so the check compared an unchanged README. Easy to add before pushing.

## Resolved

- 2026-10-30 (R7): Clean-clone check done (docs/R7_reproducibility.md): every file in results/, docs/ and the
  README reproduces, R2 within a 1e-9 relative tolerance (config/reproducibility.yaml), which settles the R6
  item on R2's last digits for the check. The download-retry item (R1) did not come up: nothing was downloaded.

- 2026-10-29 (R6): The report keeps the pre-set recommendation (Sebastián Cristóforo) with the two-route
  framing already in the executive summary; no change to the recommendation rule (Aradhya). The README
  and the dashboard repeat the two routes.
- 2026-10-29 (R6): Hindsight trim. results/r1_data_report.json no longer holds Kante's valuations after
  2016-07-01 (three records, two with Chelsea) nor the "valued within 6 months either side" counts, which
  were built from valuations after the date. The R1 SQL reads nothing after the date; history now runs
  12 months up to it (config/audit.yaml). R1 re-run with the new `--audit-only` mode (existing DuckDB,
  raw-file fingerprints verified, nothing re-downloaded). tests/test_hindsight.py fails if any
  results/*.json holds a date after the valuation date or a negative days-before value (run fields exempt);
  it found only the R1 records above.
- 2026-10-29 (R6): Season label "2015/16" everywhere in docs, figures, README and dashboard, from
  config/scope.yaml season.label (season_name stays StatsBomb's "2015/2016"). R1-R5 re-rendered: R3-R5
  results identical apart from run fields; R1 changed only by the trim; R2 see TO VERIFY (last-digit
  noise). Figures unchanged (they already said 2015/16).
- 2026-10-29 (R6): StatsBomb logo in assets/statsbomb_logo.png, from the Media Pack (see TO VERIFY for
  its terms), on REPORT.md, every step note, the README and the dashboard, with the source line.

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
