# Frozen original — do not maintain this

`2025-12-09-as-published.ipynb` is the notebook that produced the numbers in
*Energies* **2025**, 18, 6448. It is kept as **evidence of what the paper did**,
not as a working copy.

The date in the filename is the publication date and marks it append-only: it
is never rewritten. The maintained implementation is `src/erev_vmtalloc/`.

## Do not

- Tidy it, reformat it, or split its single cell.
- Fix its bugs. It has at least one that reached print — see README.md,
  "Known defect: the scenario weights are a hardcoded fallback". Fixing it here would
  destroy the only record of what produced the published scenario numbers.
- Strip its outputs. They are the published run.
- Re-execute it. It calls the BTS and Census APIs live, so re-running it now
  produces different inputs, and the Census data call no longer works without
  an API key at all.

## Do

- Read it to see what the paper did.
- Put corrections in `src/`, and record the divergence in the README's
  "Stated residuals" or "Known defect" section.

## Does `src/` still agree with it?

Yes, and that is enforced rather than asserted. The package reproduces the
notebook's output exactly across all twenty range/scenario combinations;
`tests/test_paper_numbers.py` pins the two figures the abstract quotes, and
`tests/test_acs_lookup.py` pins the fallback weights that drove the scenarios.

Run `pytest` to check. If those go red, `src/` has drifted from what was
published and the divergence needs recording — it is not a test to relax.
