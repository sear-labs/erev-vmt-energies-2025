# erev-data-energies-2025 conventions

The portable standard governs this repo. Read it before working here:

    https://github.com/sear-labs/code-standard    canonical - same from any machine
    a local clone, if you have one                faster; check the branch before quoting it

**Read it first and last.** Nothing in this file restates it - no summary, no
quick-reference table. If a rule you need is not below, it is in the standard,
not missing.

---

# Part 11 - This project specifically

## What this is

The code behind one published paper:

> Patil, H.V., Kumbhar, A.A. & Jones, E.C., Jr. "Contributions of
> Extended-Range Electric Vehicles (EREVs) to Electrified Miles, Emissions and
> Transportation Cost Reduction." Energies 2025, 18, 6448.
> https://doi.org/10.3390/en18246448

**Archetype A**, not P. The original is Python, so publishing it does not make
it a reimplementation; it takes the journal-and-year suffix and stays A.

## The four axes (Part 2c)

| axis | answer |
|---|---|
| Sensitivity | Public federal data, published open-access paper. Nothing restricted. Cleared by Jones to go public (2026-09-14); the licence choice already anticipates it. |
| Actively developed | Yes for `src/`, no for `notebooks/`. Git is correct. |
| In a syncing folder | No. Every clone lives in a developer folder outside OneDrive. Where the original source material sits is recorded in `notebooks/README.md`, not here. |
| Devices that edit | More than one, each a plain clone of the GitHub remote. That is safe because no clone is in a syncing folder, so no pointer treatment is needed. |

**No machine paths in committed files.** `scripts/check_no_machine_paths.py` fails the
suite on a home directory, a drive-letter path or a personal SharePoint URL in any
tracked file, including inside `.xlsx` workbooks. Describe a location in words
("a developer folder outside OneDrive"), never by its path.

## Layout that is not obvious from the tree

- `notebooks/2025-12-09-as-published.ipynb` is **frozen evidence**, not a
  maintained copy. It is what produced the published numbers, shipped with its
  outputs. Do not tidy it, do not refactor it, do not fix its bugs. Corrections
  go in `src/` and the divergence is recorded in the README.
- `data/raw/` is committed on purpose and is small. The published notebook
  called the BTS and Census APIs at run time; that made the paper's inputs
  mutable, so they are frozen here with provenance sidecars and a manifest.
- `config/base.yaml` holds every constant that was a module-level global in the
  notebook. A scenario change is an edit here, never a copy of a script.

## The one thing to know before changing anything

`charging.weights_source` defaults to `published_fallback`. That is **not** what
the notebook was written to do (weight households from Census ACS B25032); it is
what it actually did, because its ACS lookup matched zero variables and fell
through to a hardcoded vector. The paper itself never says how the weights were set.
See README, "Scenario weights". Changing the default silently changes published
scenario numbers.

## Conventions local to here

- Bin labels use an ASCII hyphen (`"0-1"`), never an en-dash. The label is a
  join key across three files.
- Anything asserting a number from the paper lives in
  `tests/test_paper_numbers.py` and names the sentence it defends.
- Residuals that are known and unexplained are listed in the README under
  "Stated residuals". An unexplained residual that is not written down is
  indistinguishable from an unfound bug - so add to that list rather than
  leaving a TODO.

## Exemptions taken

- **No CI matrix across Python versions.** This is an analysis pinned to one
  published result, not a library with outside consumers. One version, pinned.
- **`results/` is committed** (Part 1 rule 5 exception), so a reader sees the
  paper's tables and figures without installing anything.
