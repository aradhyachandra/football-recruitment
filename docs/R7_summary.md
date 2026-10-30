# R7: Dashboard polish, clean-clone check and portfolio page (plain-language note)

<img src="../assets/statsbomb_logo.png" alt="Hudl StatsBomb logo" width="220">

**Dashboard.** The budget slider now reads in millions of euros, and the wide tables show every
column without scrolling: fewer columns, shorter headers (the full name appears on hover), and the
Explore lists use the full page width. Similarity stays in every player list. Which columns are hidden,
and why, is written in `config/publication.yaml`. The two screenshots in `docs/figures/` were re-taken.

**Clean-clone check.** The repository was cloned into an empty folder, set up from scratch and run from
start to finish on the existing download. Every file in `results/`, `docs/` and the README came out the
same, apart from run times, memory and tiny rounding noise in one step's sums. One test failed in the
clone, and it found a real gap in `.gitignore`, now fixed. Details and figures:
[R7_reproducibility.md](R7_reproducibility.md).

**Portfolio page.** A case-study page for this project was added to the portfolio site (a separate
repository, nothing committed there). Every number on it was recomputed from `results/` by a script;
the list is in [R7_portfolio_numbers.md](R7_portfolio_numbers.md).

As everywhere in this project, the shortlist describes a similar profile under stated assumptions, not
a forecast of how any player would do at another club.
