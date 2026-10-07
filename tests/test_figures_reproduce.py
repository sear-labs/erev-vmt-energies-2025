"""The package's figure data against what the published figures actually drew.

tests/fixtures/notebook_figures.csv holds every bar and dot the frozen Fall 2025
notebook plots in the published version of Figures 2-3 and 5-13, recorded by
scripts/capture_notebook_figures.py. This compares erev_vmtalloc.costs.figure_data with
it, value for value, in the figures' own units.

This is a stronger claim than tests/test_workbook_agreement.py makes: the notebook
does its own arithmetic between the workbook and the plot (unit changes, and for
Figure 7 a whole ICE and EV bar computed in the cell), and that is checked here too.

Tolerance: 2e-5 relative, for the same reason as the charging sheet there (the
7-a-week gas VMT is pasted in the workbook and derived here). Figure 1 is not covered;
see notebooks/README.md.

Figure 4's rows in the fixture are what the frozen notebook draws once its missing
inputs are supplied from the recovered rule (scripts/capture_notebook_figures.py). That
shows the package and the notebook simulate the week identically. Whether the
recovered inputs are the ones the published figure used is a separate question,
answered by test_figure4_matches_the_published_image against measurements of it.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from erev_vmtalloc import costs

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "notebook_figures.csv"
REL_TOL = 2e-5


def test_every_plotted_value_reproduces(fitted, config):
    ours = pd.concat([
        costs.figure_data(costs.scenario_table(fitted, config),
                          costs.charging_table(fitted, config, ROOT / "data" / "raw"), config),
        costs.figure4_data(fitted, config),
    ], ignore_index=True)
    # Figure 1's CO2 bars are typed into its cell to three decimals, so they are
    # compared separately, at that precision (test_figure1_reproduces).
    drawn_all = pd.read_csv(FIXTURE, dtype={"x": str}, float_precision="round_trip")
    assert (drawn_all.figure == 1).sum() == 20, "Figure 1 rows missing from the fixture"
    drawn = drawn_all[drawn_all.figure != 1]
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


MEASURED = ROOT / "tests" / "fixtures" / "article" / "figure4_measured.csv"
# One pixel of the published image is 0.38 miles; allow 2.6 pixels for edge
# antialiasing and dot rendering. The calibration row reads 0.24 high.
IMAGE_TOL_MILES = 1.0


def _figure4_value(fig4, row):
    series = f"{row.charges_per_week}/week R={row.range_mi} {row.quantity}"
    hit = fig4[(fig4.series == series) & (fig4.x == row.day)]
    assert len(hit) == 1, series
    return float(hit.y.iloc[0])


def test_figure4_matches_the_published_image(fitted, config):
    """The recovered weekly profile reproduces the published Figure 4 as measured.

    The test is shown to discriminate: the obvious alternative input, trips per
    household computed from the 131.4 M households in Table 4, misses the weekday bar
    by more than the tolerance, and Section 4.6's own rule (leave out trips over 100
    miles) misses by 17 miles.
    """
    fig4 = costs.figure4_data(fitted, config)
    measured = pd.read_csv(MEASURED)
    for row in measured.itertuples():
        ours = _figure4_value(fig4, row)
        print(f"{row.charges_per_week}/wk R={row.range_mi} {row.day} {row.quantity:<20} "
              f"image {row.measured:7.2f}  package {ours:7.2f}  gap {ours - row.measured:+.2f}")
        assert abs(ours - row.measured) <= IMAGE_TOL_MILES

    weekday = float(costs.weekly_profile(fitted, config)[0])
    published_weekday = float(measured.measured.iloc[0])
    per_household = (fitted.annual_trips_billion / 52 * 1000
                     / config["paper_scenarios"]["households_millions"])
    alt = 0.14 * float((per_household * fitted.mean_distance).sum())
    short = costs.weekly_trips_per_household(fitted, config)[:7] * fitted.mean_distance[:7]
    text_rule = 0.14 * float(short.sum())
    print(f"weekday miles: recovered {weekday:.2f}, from households {alt:.2f}, "
          f"under-100-mile trips only {text_rule:.2f}, image {published_weekday:.2f}")
    assert abs(alt - published_weekday) > IMAGE_TOL_MILES
    assert abs(text_rule - published_weekday) > 10



def test_figure1_reproduces(fitted, config):
    """Figure 1's CO2 bars, computed from the workbook's inputs, round to the three
    decimals typed into the cell; its VMT dots are the cell's values."""
    drawn = pd.read_csv(FIXTURE, dtype={"x": str}, float_precision="round_trip")
    drawn = drawn[drawn.figure == 1]
    ours = costs.figure1_data(costs.scenario_table(fitted, config), fitted, ROOT / "data" / "raw")
    m = drawn.merge(ours, on=["figure", "series", "x"], suffixes=("_drawn", "_ours"))
    assert len(m) == 20, len(m)
    for row in m.itertuples():
        print(f"{row.series:<9} {row.x:<26} drawn {row.y_drawn:9.4f}  package {row.y_ours:9.4f}")
    co2 = m[m.series == "CO2 (Bt)"]
    assert ((co2.y_ours - co2.y_drawn).abs() <= 5e-4 + 1e-9).all()
    vmt = m[m.series == "VMT (T)"]
    # Recovered from the plot through the axis transform, so not bit-exact.
    assert ((vmt.y_ours - vmt.y_drawn).abs() / vmt.y_drawn <= 1e-9).all()
