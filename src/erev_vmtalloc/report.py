"""Tables and figures.

The paper's tables are "display-exact": the VMT column is the product of the
other two columns *as printed*, so a reader who multiplies what they see gets
what they see. That is a presentation choice, and it is reconstructed here
rather than recomputed from full precision.

The original notebook guarded this with an assertion that compared the
displayed product against `round(trips_disp * avg_disp, 3)` -- the same
expression that produced it. A check that recomputes its own definition agrees
with itself and cannot fail. `check_display_consistency` below compares the
displayed product against the *full-precision* VMT instead, which is the claim
worth defending: that rounding for display did not move a number materially.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # No display in CI or on a headless clean clone.

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .allocation import FittedVmt  # noqa: E402

# The check is on the TABLE TOTAL, relative, not on each bin.
#
# Per-bin is the wrong altitude here and measurement says so. The 0-1 mile bin
# fits at exactly 0.25 miles and displays as 0.3 -- a one-decimal rounding that
# inflates that bin's shown VMT by 20% (43.942 B against 36.618 B). That is
# real and it is in the published Table 1, but it is 0.2% of a 3385 B total and
# it moves no conclusion. A per-bin gate tight enough to catch a genuine error
# fires on that every run, and a check that fires on known-acceptable behaviour
# gets deleted, taking the real guard with it.
#
# Measured 2026-09-10: actual total drift is +0.222%. The 1% gate has room for
# ordinary rounding and would still catch a bin dropped or double-counted.
DISPLAY_TOLERANCE_PCT = 1.0


def check_display_consistency(
    displayed: np.ndarray, full_precision: np.ndarray, label: str
) -> None:
    """Fail if rounding for display moved the table's total materially."""
    shown, exact = float(displayed.sum()), float(full_precision.sum())
    drift_pct = 100.0 * (shown - exact) / exact
    if abs(drift_pct) > DISPLAY_TOLERANCE_PCT:
        raise AssertionError(
            f"{label}: display rounding moved the table total by {drift_pct:+.3f}% "
            f"(displayed {shown:.3f} B vs full precision {exact:.3f} B); "
            f"tolerance is +/-{DISPLAY_TOLERANCE_PCT}%."
        )


def monthly_fit_table(fitted: FittedVmt) -> pd.DataFrame:
    """FHWA target against the fitted model, month by month, before normalizing."""
    modelled = fitted.vmt_miles_prenorm.sum(axis=1) / 1e9
    return pd.DataFrame(
        {
            "Month": fitted.months,
            "FHWA VMT (B)": np.round(fitted.fhwa_billion, 3),
            "Model VMT (B) (pre-norm)": np.round(modelled, 3),
            "Error (%) (pre-norm)": np.round(fitted.monthly_error_pct(prenorm=True), 2),
        }
    )


def month_table(fitted: FittedVmt, month: int) -> pd.DataFrame:
    """Table 1 of the paper: one month, trips and mean distance by bin."""
    if month not in fitted.months:
        raise ValueError(f"Month {month} not in fitted months {fitted.months}")
    row = fitted.months.index(month)

    trips_billion = fitted.trips[row] / 1e9
    trips_disp = np.round(trips_billion, 3)
    distance_disp = np.round(fitted.mean_distance, 1)
    vmt_disp = np.round(trips_disp * distance_disp, 3)

    check_display_consistency(vmt_disp, trips_billion * fitted.mean_distance, f"Month {month}")

    return pd.DataFrame(
        {
            "Trip Distance Bin (miles)": fitted.bins,
            "Trips (B/month)": trips_disp,
            "Calculated Average Bin Distance (miles)": distance_disp,
            "Calculated VMT (B)": vmt_disp,
        }
    )


def annual_table(fitted: FittedVmt) -> pd.DataFrame:
    """Annual equivalent of Table 1, summed over months. Pre-normalization."""
    trips_billion = fitted.annual_trips_billion
    trips_disp = np.round(trips_billion, 3)
    distance_disp = np.round(fitted.mean_distance, 1)
    vmt_disp = np.round(trips_disp * distance_disp, 3)

    check_display_consistency(vmt_disp, trips_billion * fitted.mean_distance, "Annual")

    return pd.DataFrame(
        {
            "Trip Distance Bin (miles)": fitted.bins,
            "Trips (B/year)": trips_disp,
            "Average Bin Distance (miles)": distance_disp,
            "Calculated VMT (B/year)": vmt_disp,
        }
    )


def _save(fig_dir: Path, name: str) -> Path:
    path = fig_dir / name
    plt.tight_layout()
    plt.savefig(path, dpi=200)
    plt.close()
    return path


def write_figures(summary: pd.DataFrame, fig_dir: Path) -> list[Path]:
    """Regenerate every figure from the base-case summary table."""
    fig_dir.mkdir(parents=True, exist_ok=True)
    ranges = summary["Range (mi)"].to_numpy()
    written = []

    plt.figure()
    plt.plot(ranges, summary["$ / ton CO2 saved"], marker="o")
    plt.xlabel("EV range (miles)")
    plt.ylabel("Cost per ton CO$_2$ saved ($/ton)")
    plt.title("Cost per ton of CO$_2$ saved vs EV range")
    written.append(_save(fig_dir, "cost_per_ton.png"))

    plt.figure()
    plt.plot(ranges, summary["$ / electric mile"], marker="o")
    plt.xlabel("EV range (miles)")
    plt.ylabel("Cost per electric mile ($/mile)")
    plt.title("Cost per electric mile vs EV range")
    written.append(_save(fig_dir, "cost_per_electric_mile.png"))

    plt.figure()
    plt.plot(ranges, summary["EV VMT (B)"], marker="o", label="EV VMT (B)")
    plt.plot(ranges, summary["Gas VMT (B)"], marker="o", label="Gas VMT (B)")
    plt.xlabel("EV range (miles)")
    plt.ylabel("VMT (billion miles)")
    plt.title("Electric vs gasoline VMT by EV range (annual)")
    plt.legend()
    written.append(_save(fig_dir, "ev_vs_gas_vmt.png"))

    plt.figure()
    gas = summary["Gas VMT (B)"].to_numpy()
    ev = summary["EV VMT (B)"].to_numpy()
    plt.bar(ranges, gas, label="Gas VMT (B)")
    plt.bar(ranges, ev, bottom=gas, label="EV VMT (B)")
    plt.xlabel("EV range (miles)")
    plt.ylabel("VMT (billion miles)")
    plt.title("VMT split by EV range")
    plt.legend()
    written.append(_save(fig_dir, "vmt_split_bars.png"))

    plt.figure()
    plt.plot(ranges, summary["EV CO2 saved (Mt)"], marker="o")
    plt.xlabel("EV range (miles)")
    plt.ylabel("CO$_2$ saved (Mt)")
    plt.title("Annual CO$_2$ savings vs EV range")
    written.append(_save(fig_dir, "carbon_savings_vs_range.png"))

    plt.figure()
    plt.plot(ranges, summary["kWh battery / electric mile"], marker="o")
    plt.xlabel("EV range (miles)")
    plt.ylabel("kWh of battery per electric mile")
    plt.title("Installed battery intensity vs EV range")
    written.append(_save(fig_dir, "battery_intensity.png"))

    return written
