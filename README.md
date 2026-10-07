# erev-data-energies-2025

How much of US vehicle travel could an extended-range electric vehicle (EREV)
drive on battery, as a function of its electric range and how often it charges?

This repository is the code and frozen inputs behind:

> Patil, H.V., Kumbhar, A.A. & Jones, E.C., Jr. "Contributions of
> Extended-Range Electric Vehicles (EREVs) to Electrified Miles, Emissions and
> Transportation Cost Reduction." *Energies* **2025**, 18, 6448.
> https://doi.org/10.3390/en18246448

Conventions follow the [sear-labs code standard](https://github.com/sear-labs/code-standard);
what is specific to this project is in [CLAUDE.md](CLAUDE.md).

## How to cite

```bibtex
@article{Patil2025EREV,
  author  = {Patil, Hritik Vivek and Kumbhar, Akhilesh Arunkumar and Jones, Jr., Erick C.},
  title   = {Contributions of Extended-Range Electric Vehicles ({EREVs}) to
             Electrified Miles, Emissions and Transportation Cost Reduction},
  journal = {Energies},
  volume  = {18},
  number  = {24},
  pages   = {6448},
  year    = {2025},
  doi     = {10.3390/en18246448}
}
```

`CITATION.cff` in the repo root drives GitHub's "Cite this repository" button.

## Run it

Requires Python 3.11–3.13. No network, no API key.

```bash
python -m venv .venv && .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python scripts/run_all.py                        # the one entry point
pytest                                           # every check below
```

To check the paper's numbers without installing anything that runs the model, open
[`notebooks/verify.ipynb`](notebooks/verify.ipynb): it is committed with its outputs, needs no
network and no API key, and compares the package with the article table by table.

`run_all.py` reads the frozen snapshots in `data/raw/` and writes
`results/tables/` and `results/figures/`. It never writes to `data/raw/`.

Expected output at the base case:

```
  R=   50 mi   EV share  73.28%   EV   2391.1 B   gas   871.7 B
  R=   75 mi   EV share  78.18%   EV   2551.0 B   gas   711.8 B
  R=  100 mi   EV share  83.09%   EV   2710.9 B   gas   551.9 B
  R=  125 mi   EV share  84.94%   EV   2771.6 B   gas   491.2 B
  R=  150 mi   EV share  86.80%   EV   2832.2 B   gas   430.6 B
```

73.28% and 86.80% are the paper's 73.3% and 86.8%.
`tests/test_paper_numbers.py` asserts them, so a refactor that moves them fails
the suite rather than quietly changing a published result.

## What it does

1. **Fit.** BTS reports national monthly trip *counts* by distance bin, but not
   the miles in each bin. A bounded least-squares fit chooses one average
   distance per bin — the same vector for all twelve months — so the implied
   VMT reproduces FHWA's monthly totals. Each bin's average is constrained to
   lie inside the bin.
2. **Allocate.** At electric range *R*, a bin whose average trip is *d* miles
   can be driven electrically for `min(1, R / 2d)` of its miles. The factor of
   two is the base case: no charging at the destination, so the battery covers
   the trip out and back.
3. **Cost it.** Apply fuel economy, grid intensity, pack efficiency and pack
   cost to get emissions saved, battery installed and dollars per ton.
4. **Constrain charging.** Households sit on a ladder from `none` to `everyday`
   charging. A scenario turns that into a fleet-average charges-per-week, which
   caps annual electric miles. (These *Normal*, *Low* and *More* scenarios are this
   repository's; the paper does not use them.)
5. **The paper's scenarios.** `costs.py` is the Fall 2025 workbook's model: *Worst*,
   *Average* and *Best* parameter sets (Tables 4–6), and 7, 5, 3 and 2 charges a week
   (Figures 5, 7, 9, 11, 13). It reads the split from step 2 and `paper_scenarios` in
   `config/base.yaml`.

## Inputs

| file | source | what |
|---|---|---|
| `data/raw/bts_trips_2023.json` | [BTS Trips by Distance](https://data.bts.gov/resource/w96p-f2qv.json) | national monthly trip counts, 10 distance bins |
| `data/raw/fhwa_vmt_2023.csv` | FHWA Traffic Volume Trends | monthly VMT targets, billions of miles |
| `data/raw/acs_b25032.json` | Census ACS 1-year B25032 | tenure by units in structure — **optional**, see below |
| `data/raw/charging_gas_vmt_2023.csv` | the frozen Fall 2025 workbook | gas VMT at 5, 3 and 2 charges a week: pasted constants with no surviving generator (see its sidecar) |

Each snapshot carries a `.meta.yaml` sidecar naming its source URL, fetch date
and SHA-256, and `MANIFEST.sha256` covers all of them.
`tests/test_smoke.py::test_inputs_are_not_modified` recomputes it.

### Refreshing inputs

`python scripts/fetch_sources.py --refresh` re-fetches from the live APIs. This
**replaces the paper's inputs with today's data** and the published numbers will
no longer reproduce. It is not part of `run_all.py` and CI does not run it.

The ACS snapshot is optional and absent by default. Fetching it needs a free
[Census API key](https://api.census.gov/data/key_signup.html) in `CENSUS_API_KEY`
or a `.env` file (gitignored — never commit it). The paper's numbers do not need
it; see below for why.

## What is deliberately committed

Against the usual rule that generated files stay out of git:

- **`results/tables/` and `results/figures/`** — so a reader sees the paper's
  outputs without installing anything.
- **`data/raw/`** — small, public, immutable. Without it a clean clone cannot
  reproduce the paper offline, which is the property that actually matters.
- **`notebooks/2025-12-09-as-published.ipynb` and `notebooks/fall-2025/`, with
  outputs intact** — evidence of what produced the published numbers: the first for
  Tables 1–3, the Fall 2025 notebook and workbooks for Tables 4–6 and the figures.
  Frozen: not maintained, not refactored, not bug-fixed, and hashed in
  `notebooks/MANIFEST.sha256`. Corrections go in `src/`. See
  [`notebooks/README.md`](notebooks/README.md) for where each came from.
- **`tests/fixtures/`** — the article's printed tables, and every value the frozen
  notebook plots, so the suite can check both without the network or the notebook.

## What reproduces, and what doesn't

Checked on 2026-10-07 against the article as published on mdpi.com. Every claim below is a test,
named in brackets.

### Reproduces

- **Tables 1, 5 and 6: every printed cell.** 519 cells, each the package's number rounded to the
  printed precision. [`test_table1_every_cell`, `test_table5_every_cell`,
  `test_table6_every_cell`]
- **Tables 2 and 3: every printed cell, but 19 of 116 are truncated rather than rounded.** January's
  modelled VMT is 278.367 B and prints as 278.36. Those 19 cells are listed by name, and each must
  truncate and must not round, so the list can't go stale. [`test_table2_every_cell`,
  `test_table3_every_cell`]
- **31 numbers quoted in the prose**, from the summary, Section 4.3 and the conclusions.
  [`test_prose_numbers_reproduce`]
- **Figures 2, 3 and 5–13: every plotted value.** 440 bars and dots match what the frozen notebook
  draws, to within 8e-6. [`test_figures_reproduce.py`]
- **The workbook behind Tables 4–6 and the figures, cell by cell.** 1,403 cached formula values.
  [`test_workbook_agreement.py`]

Tables 5–6 and Figures 2–3 and 5–13 come from the Fall 2025 workbook, now frozen in
`notebooks/fall-2025/`. Its model is reimplemented in `src/erev_vmtalloc/costs.py`, with its inputs
in `config/base.yaml` under `paper_scenarios`.

### Doesn't reproduce

- **Figure 4.** Its notebook cell falls back to a hardcoded week (35, 40, 30, 45, 25, 70, 55 miles),
  because it looks for variables the notebook never defines. The published figure shows about 73
  miles a weekday and 77 a weekend day, from inputs that weren't saved.
- **The 5-, 3- and 2-day charging inputs.** These are pasted constants in the workbook. Nothing that
  generated them survives in the notebook, either workbook, or the students' `EV-Analysis`
  repository. They are in `data/raw/charging_gas_vmt_2023.csv`, and everything downstream of them
  reproduces, but they can't be checked themselves.
- **"Up to 75% of potential electrified miles" lost below five charges a week** (conclusions). The
  largest loss the workbook computes is 39%: two charges a week against seven, at 25 miles.
  [`test_up_to_75_percent_loss_is_not_in_the_workbook`]
- **Figure 1** is not checked. Its CO2 bars are typed into the cell. Its VMT dots for rail,
  watercraft, aircraft, non-transport vehicles and pipelines are labelled "placeholders" in the
  cell, and the placeholders are what was published.

### The charging figures use a VMT total about 4% higher than the tables

- **Tables 2–3 and 5–6 and the scenario figures (2, 3, 6, 8, 10, 12) use FHWA's 3,262.8 B miles.**
- **The charging-frequency figures (5, 7, 9, 11, 13) use 3,392.5 B, the sum of Table 1's printed VMT
  column.** That is 3.97% higher. 3.74 points of it are the fit before it is normalised to FHWA
  (residual 4 below). The other 0.22 points are the 0–1 mile bin's display rounding (residual 3).
- **So the 7-a-week case has the same electric share as the Average scenario, but 3.98% more
  electric miles at every range.** At 25 miles that is 2,013.7 B against 1,936.7 B. Section 4.6
  says the opposite: that the scenarios have "slightly more electric VMT".
  [`test_daily_charging_runs_four_percent_above_the_average_scenario`]
- **Figure 11's CO2 savings mix the two totals.** They subtract emissions on the 3,392.5 B total from
  an ICE baseline on 3,262.8 B, so every saving there is understated. At 50 miles and seven charges
  a week, Figure 11 shows 553.0 Mt saved where Table 5 has 573.9 Mt.
- **Figure 7 draws its own ICE bar on 3,392.5 B**: 1.142 Bt of CO2, where Figure 6's Average ICE
  bar is 1.098 Bt.
- **The published numbers are kept as published.** `config/base.yaml`
  (`paper_scenarios.charging.vmt_basis: normalized`) gives the consistent version.

### Other places the article disagrees with itself

None of these is corrected. Each is pinned by a test that fails if the code changes so the
disagreement disappears.

| where | printed | what produced the published numbers |
|---|---|---|
| Table 4, CO2 per gallon | 8.887 kg | 8.888 kg in every workbook row and every Table 5 value |
| Table 4, vehicle count | 286.1 M | 257.7 M (2022 light-duty vehicles); 286.1 M would make Table 6's 3.6 TWh read 4.0 |
| Table 4, fuel economy, grid intensity, electricity price | listed under "Worst/Average/Best" | listed in Best/Average/Worst order (Worst used 36 mpg, 714 g/kWh, $0.40/kWh) |
| Table 4, battery pack cost | absent; the text gives $115/kWh | Worst $150, Average $115, Best $75 |
| Table 6, Average EV row | $OPEX 135.95, $0.042/mi | priced at $0.15/kWh where every other Average row uses $0.25; at $0.25 it is 226.58 |
| Summary, CAPEX per kg at 150 mi | 1.82 USD/kg | 0.182, as Table 6 and the conclusions print |
| Summary, CO2 saved at 150 mi | 679 Mt | 679.73, which the conclusions print as 680 |
| Section 4.3, CAPEX per electric mile and per ton | $0.161 and $0.409/mi; $712 and $1,802/t | a different model, `metrics.summarize` (one year, a 241.8 M fleet, 26.2 mpg, 387 g/kWh). Table 6's figures for the same cases are about a tenth of these |
| Section 4.3, "Fleet Wh Battery Capacity per electric VMT" | "USD 1.097" | 1.097 Wh of installed battery per mile of *total* VMT; neither dollars nor per electric mile |
| Figure 5 caption | "(B)" | the axis is in trillions |
| Figure 6 caption | "CO2 savings" | the bars are emissions, not savings |

*Corrected 2026-10-07. On 2026-10-06 this section said Tables 4–6 and Figures 2–13 did not
reproduce, because the workbook and notebook behind them weren't in the repository yet. Before that,
the 2026-10-01 README said "the paper's numbers reproduce exactly", which was true of Tables 1–3
only.*

## Scenario weights

This note is about what the code could do but doesn't.

- **The *Normal*, *Low* and *More* scenarios weight households by how they can charge:** garage,
  driveway, work or weekly public charging.
- **Those weights are fixed: 45%, 25%, 20%, 10%.** The notebook tried to take them from Census table
  B25032 (housing tenure by units in structure), but its lookup matched no variables, so it used
  the fixed values.
- **The paper is consistent with this.** Section 3.4 doesn't say where the weights came from.
- **They change only 1 of 15 results:** *Low* at a 50-mile range (62.61% electric). The rest are
  uncapped and don't use the weights.
- **Census weights are available** with a free Census API key: set `CENSUS_API_KEY`, run
  `scripts/fetch_sources.py`, and set `charging.weights_source: acs_b25032` in `config/base.yaml`.
  This hasn't been run, so how much the *Low* 50-mile result would change is unknown. It will not
  reproduce the paper.

Why the notebook's lookup matched nothing (pinned in `tests/test_acs_lookup.py`):

| it looked for | the Census label is |
|---|---|
| `Owner occupied` | `Owner-occupied housing units` |
| `!!Estimate` anywhere | `Estimate!!` at the start |
| `2 apartments`, `3 or 4 apartments` | `2`, `3 or 4` |

## Stated residuals

Known, measured, and unexplained. Listed because an unexplained residual that
is not written down cannot be told apart from an unfound bug.

1. **Every fitted bin distance sits exactly on its lower bound** — all ten:
   0.25, 1, 3, 5, 10, 25, 50, 100, 250, 500. The bounded least squares has no
   interior optimum; it wants shorter distances than the bins allow and is
   clamped everywhere. So Table 1's "calculated average bin distance" column is
   the configured bin floors, and the EV share reduces to
   `min(1, R / 2·floor)` per bin. The fit contributes the *choice of floors*,
   not an estimate. `tests/test_invariants.py::test_fit_is_pinned_at_lower_bounds`
   pins this so it cannot change unnoticed.
2. **The abstract's "13.7 kWh battery" for a 50-mile range does not follow from
   the configured efficiency.** `50 / 3.6 = 13.89 kWh`; 13.7 implies
   3.65 mi/kWh. Which is intended is a question for the authors.
3. **The 0–1 mile bin's displayed average rounds 0.25 up to 0.3**, inflating
   that bin's shown VMT by 20% (43.942 B against 36.618 B full precision). It
   is 0.2% of the 3385 B table total and moves no conclusion, but it is in the
   published table.
4. **Pre-normalization the fit is 3.74% high on the annual total** and up to
   11.84% off in a single month. `normalize_to_fhwa: true` rescales each month
   to its FHWA target, which is what the paper used.
5. **The `500+` bin is capped at 1000 miles by assumption.** It is open-ended in
   the source data. It carries 256.5 B miles, so the assumption is load-bearing
   for the longest-range results.
6. **The workbook's 7-a-week gas VMT is within 8e-6 of what this package derives,
   not exact.** The package takes the base-case gas share times 3,392.497 B. The
   workbook's pasted values imply totals drifting from 3,392.493 down to 3,392.470
   across ranges, so they came from some rounded intermediate that does not
   survive. At most 0.0036 B miles, far below anything printed; the agreement
   tests allow 2e-5 and say why.

## Licence

Two licences, because one does not cover the other's files.

| path | licence |
|---|---|
| `src/`, `scripts/`, `tests/` | MIT — see [LICENSE](LICENSE) |
| `data/`, `results/`, `notebooks/` | CC BY 4.0 — see [LICENSE-DATA](LICENSE-DATA) |

The paper itself is CC BY 4.0 from MDPI.

## Layout

```
config/base.yaml          every constant that was a notebook global
data/raw/                 frozen inputs + provenance sidecars + manifest
src/erev_vmtalloc/        the maintained implementation
  sources.py                fetch once, then read the snapshot
  allocation.py             the fit and the electric/gas split
  metrics.py                emissions, battery, cost
  scenarios.py              charging-frequency ladder and budgets
  report.py                 tables and figures
  costs.py                  the Fall 2025 workbook's model: Tables 5-6, charging figures
scripts/run_all.py        the one entry point
scripts/fetch_sources.py  the only script that touches the network
scripts/import_fall2025_evidence.py   how notebooks/fall-2025/ was imported (run once)
scripts/capture_notebook_figures.py   records what the frozen notebook plots (run once)
scripts/check_no_machine_paths.py     fails on a machine path in any tracked file
notebooks/                frozen originals, plus verify.ipynb
results/                  committed tables and figures
tests/                    every guard watched to fail
  fixtures/article/         the article's printed tables
  fixtures/notebook_figures.csv   what the published figures plot
```
