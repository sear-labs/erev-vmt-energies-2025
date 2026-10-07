# Frozen originals — do not maintain these

Everything here except `verify.ipynb` is **evidence of what produced the paper**,
*Energies* **2025**, 18, 6448. None of it is a working copy. The maintained
implementation is `src/erev_vmtalloc/`.

| file | produced | where it came from |
|---|---|---|
| `2025-12-09-as-published.ipynb` | Tables 1–3, the abstract's 73.3% and 86.8%, and the EV/gas VMT columns that Tables 5–6 copy | `searlabtransfer/EV-Analysis` `Spring_2025/src/EV_analysis_final.ipynb`, byte-identical |
| `fall-2025/Calculations Check_final.xlsx` | Tables 4–6 (its `Table 4`, `Table  5`, `Table 6` sheets are pasted values of the formulas on `Calcs by Scenario`), and the inputs to Figures 2–3, 5, 7–13 | SEAR Labs shared drive, `EV Analysis/Data` |
| `fall-2025/Calculations Check_final - Copy.xlsx` | a later save of the same workbook, rearranged, with the Figure 1 subsector sheet added. Of the published figures, only Figure 6 reads it | same folder |
| `fall-2025/EV_Graphs_Updated_Finalist.ipynb` | Figures 1–13. Figures 2, 3 and 5–13 read the workbooks; Figures 1 and 4 have their numbers typed into the cell | SEAR Labs shared drive, `EV Analysis/Fall 2025/Code` |
| `fall-2025/PROVENANCE.json` | the import record: original hashes, and what the import changed | written by `scripts/import_fall2025_evidence.py` |

The Fall 2025 files were also in `searlabtransfer/EV-Analysis` at commit `042738c`
(`Fall_2025/`), byte-identical to the drive copies, before that organisation was
deleted. They were imported on 2026-10-07.

**The import changed two things, both metadata.** Each workbook recorded the folder it
was last saved in (Excel's `absPath`, in `xl/workbook.xml`): one named a personal
OneDrive folder and the other a student's drive. That element was removed. The
`- Copy` workbook's last-modified-by field held a personal account handle; its text was
emptied. Nothing else was touched: no cell, formula or cached value.
`tests/test_frozen_evidence.py` proves it without the originals: every other zip member
is byte-identical to the original, and each edited member is the original minus one
recorded span. The notebook was copied byte for byte.

## Reading the Fall 2025 notebook

- **It holds two to four drafts of most figures.** Only the last version of each
  (headed "Updated" or "Final Update") is the published figure.
- **It was written for Colab.** Three cells read `/content/Calculations Check_final.xlsx`
  and the rest a bare filename. A copy with those three paths made relative ran top to
  bottom on a fresh kernel on 2026-10-07: 0 errors, 27 figures, 19 s. That copy was then
  discarded, because the committed file is never re-executed.
- **Figure 4 does not regenerate from this notebook alone.** Its cell looks for
  `WEEKLY_TRIPS_PER_BIN`, `bins` and `x_opt`, which this notebook never defines, so it
  falls back to a hardcoded week of 35, 40, 30, 45, 25, 70 and 55 miles. Both its stored
  output and a fresh run draw that week. The published figure was made in a kernel that
  had those variables. Their values were recovered on 2026-10-07 (config
  `paper_scenarios.weekly_profile`): with them supplied, this cell draws the published
  figure. `scripts/capture_notebook_figures.py` does exactly that, in a temporary copy.
- **Figure 1's VMT dots for five modes are placeholders.** The cell labels the values
  for rail, watercraft, aircraft, non-transport vehicles and pipelines "placeholders
  (update if you have official values)", and the published figure plots them. At the
  figure's 3.5-trillion scale they sit at or near zero; pipelines shows at 0.02.
- **The 5-, 3- and 2-day charging inputs are typed constants** in the workbook's
  `Calcs by Charge` sheet (`D8:D25`). Nothing that produced them survives here or in
  `searlabtransfer/EV-Analysis`. A rule that reproduces all 18 was recovered on
  2026-10-07 (config `paper_scenarios.charging.missed_charge_loss`), and the package
  uses it.

## Do not

- Tidy, reformat or re-execute any of these files, or strip their outputs. Every
  file is hashed in `MANIFEST.sha256`, and `tests/test_frozen_evidence.py` fails the
  suite if one changes.
- Fix their bugs. Several reached print; see the README. Fixing one here would destroy
  the only record of what produced the published numbers.
- Open and save a workbook in Excel. That rewrites every member and fails the test,
  correctly.
- Add a file here without recording it. The same test fails on any file under
  `notebooks/` that is neither frozen nor named as maintained.

## Do

- Read them to see what the paper did.
- Put corrections in `src/`, and record the divergence in the README's "Stated
  residuals" or "What reproduces, and what doesn't" sections.
- To check the paper without running any of this, open `verify.ipynb`. It needs no
  network and no API key.

## Does `src/` still agree with them?

Yes, and that is enforced rather than asserted.
`tests/test_paper_numbers.py` checks the package against the article's printed
tables, and `tests/test_workbook_agreement.py` checks it against the workbook's
cached values cell by cell. If either goes red, `src/` has drifted from what was
published. That is not a test to relax.
