# R6: Publication fixes, dashboard and README

<img src="../assets/statsbomb_logo.png" alt="Hudl StatsBomb logo" width="220">

*A short plain-language note; the figures live in `results/`, the README and `docs/REPORT.md`.*

## What changed, in plain words

- **No hindsight in public files.** The data audit used to list Kanté's market values for a year after
  the summer window, including his first Chelsea valuations, and counted players valued "within six
  months either side" of the window. Both used information from after the date the club would have been
  shopping, so both are gone. A new test reads every file in `results/` and fails if anything is dated
  after the valuation date.
- **One season label.** Every document, figure, the README and the dashboard now say "2015/16", from a
  single setting in `config/scope.yaml`. All earlier documents were re-rendered; their numbers did not
  change.
- **The StatsBomb logo.** The official logo from StatsBomb's Media Pack is in `assets/`, unchanged, and
  sits on the report, every step note, the README and the dashboard, with a source line.
- **A local dashboard** (`streamlit run app/streamlit_app.py`). The Case view shows Kanté's profile
  against other central midfielders, similarity against price with the shortlist, and the players who
  stay near the top under every assumption tested. The Explore view lets you pick any regular player,
  see where he ranks within his role and who is most like him, and move the weights, budget and age
  range. It reuses the tested R4 code rather than redoing the maths, and with the default settings and
  Kanté selected it gives exactly the R4 lists (a test checks this).
- **A README** rendered from saved results, like the report, and an MIT licence for the code only (the
  data is not included and not covered).

## What to keep in mind

Every list in the dashboard is a similar profile under stated assumptions, not a forecast. The weights
were chosen for the Kanté case; for other roles they are a starting point. The dashboard is not
deployed, because the StatsBomb terms do not allow the data to be passed on.
