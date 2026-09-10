# erev-vmtalloc-energies-2025

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
pytest                                           # 24 tests
```

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
   caps annual electric miles.

## Inputs

| file | source | what |
|---|---|---|
| `data/raw/bts_trips_2023.json` | [BTS Trips by Distance](https://data.bts.gov/resource/w96p-f2qv.json) | national monthly trip counts, 10 distance bins |
| `data/raw/fhwa_vmt_2023.csv` | FHWA Traffic Volume Trends | monthly VMT targets, billions of miles |
| `data/raw/acs_b25032.json` | Census ACS 1-year B25032 | tenure by units in structure — **optional**, see below |

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
- **`notebooks/2025-12-09-as-published.ipynb` with its outputs intact** — it is
  evidence of what produced the published numbers. It is frozen: not
  maintained, not refactored, not bug-fixed. Corrections go in `src/`.

## Known defect: the paper's ACS weights are a fallback

**The scenario weights described in the paper were never computed.** The
notebook selected Census B25032 variables with

```python
if side in lab and pattern in lab and ("!!Estimate" in lab)
```

where `side` was `"Owner occupied"` and `pattern` was e.g. `"2 apartments"`.
Measured against the live API on 2026-09-10, that predicate matches **zero of
23 variables**, for three independent reasons:

| looked for | actually is |
|---|---|
| `Owner occupied` | `Owner-occupied housing units` (hyphenated) |
| `!!Estimate` | label *starts* `Estimate!!` — the substring never occurs |
| `2 apartments`, `3 or 4 apartments` | `2`, `3 or 4` |

With no matches the notebook hit its fallback, emitted a `warnings.warn`, and
returned a hardcoded `{garage: .45, driveway: .25, work: .20, weekly: .10}`.
Those are the weights behind every scenario number in the paper.

This is reproduced faithfully rather than silently corrected.
`config/base.yaml` sets `charging.weights_source: published_fallback`, so
`run_all.py` regenerates what was published. Setting it to `acs_b25032` uses the
corrected lookup instead — that path needs a Census API key and will **not**
reproduce the paper. `tests/test_acs_lookup.py` pins both the defect and the
fix, offline.

The consequence is visible in the output: the charging budget binds in exactly
one of fifteen scenario/range combinations (`Low` at 50 miles, 62.61%). Every
other combination returns the uncapped base case unchanged.

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
scripts/run_all.py        the one entry point
scripts/fetch_sources.py  the only script that touches the network
notebooks/                frozen as-published original
results/                  committed tables and figures
tests/                    24 tests, every guard watched to fail
```
