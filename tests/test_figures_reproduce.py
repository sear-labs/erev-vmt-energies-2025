"""The package's figure data against what the published figures actually drew.

tests/fixtures/notebook_figures.csv holds every bar and dot the frozen Fall 2025
notebook plots in the published version of Figures 2-3 and 5-13, recorded by
scripts/capture_notebook_figures.py. This compares erev_vmtalloc.costs.figure_data with
it, value for value, in the figures' own units.

This is a stronger claim than tests/test_workbook_agreement.py makes: the notebook
does its own arithmetic between the workbook and the plot (unit changes, and for
Figure 7 a whole ICE and EV bar computed in the cell), and that is checked here too.

Tolerance: 2e-5 relative, for the same reason as the charging sheet there (the
7-a-week gas VMT is pasted in the workbook and derived here). Figures 1 and 4 are not
covered; see notebooks/README.md.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from erev_vmtalloc import costs

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "notebook_figures.csv"
REL_TOL = 2e-5


def test_every_plotted_value_reproduces(fitted, config):
    ours = costs.figure_data(
        costs.scenario_table(fitted, config),
        costs.charging_table(fitted, config, ROOT / "data" / "raw"),
        config,
    )
    drawn = pd.read_csv(FIXTURE, dtype={"x": str}, float_precision="round_trip")
    assert len(drawn) > 400, f"only {len(drawn)} plotted values in the fixture"

    merged = drawn.merge(ours, on=["figure", "series", "x"], how="outer",
                         suffixes=("_drawn", "_ours"), indicator=True)
    only_drawn = merged[merged["_merge"] == "left_only"]
    only_ours = merged[merged["_merge"] == "right_only"]
    assert only_drawn.empty, f"plotted but not computed:\n{only_drawn.head(20)}"
    assert only_ours.empty, f"computed but never plotted:\n{only_ours.head(20)}"

    both = merged[merged["_merge"] == "both"].copy()
    both["rel"] = (both["y_ours"] - both["y_drawn"]).abs() / both["y_drawn"].abs().clip(lower=1e-12)
    for fig, group in both.groupby("figure"):
        print(f"Figure {fig:>2}: {len(group):>3} values, worst rel gap {group['rel'].max():.1e}")
    bad = both[both["rel"] > REL_TOL]
    assert bad.empty, f"{len(bad)} plotted values do not reproduce:\n" + bad[
        ["figure", "series", "x", "y_drawn", "y_ours", "rel"]].to_string()
