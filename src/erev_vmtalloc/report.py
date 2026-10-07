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


def table3(fitted: FittedVmt, electric_range: float, households_m: float, *,
           round_trip: bool = True) -> pd.DataFrame:
    """Table 3 of the paper: per-bin trips, weekly trips per household, and the split.

    Full precision. VMT is FHWA-normalised (it sums to 3,262.8 B); the average
    distance is shown at one decimal, as printed. Weekly trips are the annual count
    over 52 weeks, and per household over `households_m` million households.
    """
    from .allocation import ev_ratio_per_bin

    ratio = ev_ratio_per_bin(electric_range, fitted.mean_distance, round_trip=round_trip)
    vmt = fitted.annual_vmt_billion_per_bin
    trips = fitted.annual_trips_billion
    return pd.DataFrame(
        {
            "Trip Distance Bin (miles)": fitted.bins,
            "Avg Dist (mi)": np.round(fitted.mean_distance, 1),
            "Trips (B/yr)": trips,
            "Trips (B/wk)": trips / 52,
            "Trips/HH/wk": trips / 52 * 1000 / households_m,
            "VMT (B/yr)": vmt,
            "EV VMT (B/yr)": vmt * ratio,
            "Gas VMT (B/yr)": vmt * (1 - ratio),
            "EV% in bin": 100 * ratio,
        }
    )


def write_csv(frame: pd.DataFrame, path: Path) -> Path:
    """Write a results table with LF endings on every platform.

    `to_csv` follows the OS by default, so the same run emits CRLF on Windows
    and LF on Linux. Since results/ is committed, that makes every table differ
    between a local run and CI for reasons unrelated to any number -- and CI
    compares committed results against a fresh run to catch a moved number.
    A check that goes red on the platform rather than on the result gets
    ignored, so the artifact is made platform-independent instead.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")
    return path


def _save(fig_dir: Path, name: str) -> Path:
    path = fig_dir / name
    plt.tight_layout()
    plt.savefig(path, dpi=200)
    plt.close()
    return path


# Figures 2-3 and 5-13 of the paper, drawn from costs.figure_data (the same table that
# tests/test_figures_reproduce.py checks against what the published figures plotted).
# Each spec: bar groups (one series, or a (bottom, top) stacked pair), an optional
# secondary-axis dot series per group, and the axis labels. Styling is plain on
# purpose: the numbers are the reproduction, not the look.
_SCEN = ["Worst", "Average", "Best"]
_CPW = ["7/week", "5/week", "3/week", "2/week"]
PAPER_FIGURES = {
    2: ("Installed battery capacity vs EV range, by scenario", "Installed battery (TWh)",
        [f"{s} installed battery (TWh)" for s in _SCEN], None, None, False),
    3: ("Fleet battery capital cost vs EV range, by scenario", "Capital cost ($ trillion)",
        [f"{s} battery capital cost ($T)" for s in _SCEN], None, None, False),
    5: ("Annual VMT vs EV range, by charges per week",
        "VMT (trillion miles): electric below, gas above",
        [(f"{c} electric VMT (T)", f"{c} gas VMT (T)") for c in _CPW],
        ["dots: electric VMT if charged before each trip (T)"], None, False),
    6: ("Annual CO2 emissions vs EV range, by scenario",
        "CO2 (billion t/yr): gas below, grid above",
        [(f"{s} gas CO2 (Bt)", f"{s} grid CO2 (Bt)") for s in _SCEN], None, None, False),
    7: ("Annual CO2 emissions vs EV range, by charges per week",
        "CO2 (billion t/yr): gas below, grid above",
        [(f"{c} gas CO2 (Bt)", f"{c} grid CO2 (Bt)") for c in _CPW], None, None, False),
    8: ("Battery CAPEX per electric mile (10-year life), by scenario", "$ per electric mile",
        [f"{s} CAPEX per EV mile ($)" for s in _SCEN], [f"{s} electric VMT (T)" for s in _SCEN],
        "Electric VMT (trillion miles)", False),
    9: ("Battery CAPEX per electric mile (10-year life), by charges per week",
        "$ per electric mile", [f"{c} CAPEX per EV mile ($)" for c in _CPW],
        [f"{c} electric VMT (T)" for c in _CPW], "Electric VMT (trillion miles)", False),
    10: ("Battery CAPEX per ton CO2 saved (10-year life), by scenario", "$ per ton CO2 (log)",
         [f"{s} CAPEX per ton CO2 saved ($)" for s in _SCEN],
         [f"{s} CO2 saved (Mt)" for s in _SCEN],
         "Annual CO2 saved (Mt)", True),
    11: ("Battery CAPEX per ton CO2 saved (10-year life), by charges per week",
         "$ per ton CO2", [f"{c} CAPEX per ton CO2 saved ($)" for c in _CPW],
         [f"{c} CO2 saved (Mt)" for c in _CPW], "Annual CO2 saved (Mt)", False),
    12: ("Annual operating cost vs EV range, by scenario",
         "Operating cost ($ billion): gas below, electricity above",
         [(f"{s} gas OPEX ($B)", f"{s} electricity OPEX ($B)") for s in _SCEN], None, None, False),
    13: ("Annual operating cost vs EV range, by charges per week",
         "Operating cost ($ billion): gas below, electricity above",
         [(f"{c} gas OPEX ($B)", f"{c} electricity OPEX ($B)") for c in _CPW], None, None, False),
}


def write_paper_figures(figdata: pd.DataFrame, fig_dir: Path) -> list[Path]:
    """Figures 2-3 and 5-13 from the long-format table costs.figure_data returns."""
    fig_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for number, (title, ylabel, groups, dots, dot_label, log) in PAPER_FIGURES.items():
        data = figdata[figdata["figure"] == number]

        def series(name, data=data, number=number):
            s = data[data["series"] == name]
            if s.empty:
                raise KeyError(f"Figure {number}: no series {name!r} in figure data")
            return s.set_index("x")["y"]

        first = groups[0][0] if isinstance(groups[0], tuple) else groups[0]
        xs = list(series(first).index)
        if number == 7:  # the ICE and EV bars sit either side of the ranges
            xs = ["ICE"] + xs + ["EV"]
        width = 0.8 / len(groups)
        fig, ax = plt.subplots(figsize=(10, 5))
        hatches = ["", "//", "..", "xx"]
        for k, group in enumerate(groups):
            pos = np.arange(len(xs)) - 0.4 + width * (k + 0.5)
            label = (group[0] if isinstance(group, tuple) else group).split(" ")[0]
            if isinstance(group, tuple):
                low = series(group[0]).reindex(xs).fillna(0.0).to_numpy()
                high = series(group[1]).reindex(xs).fillna(0.0).to_numpy()
                # Grey below, blue above, as the y label says; hatching tells groups apart
                # without relying on colour.
                ax.bar(pos, low, width, color="#bdbdbd", hatch=hatches[k], edgecolor="black")
                ax.bar(pos, high, width, bottom=low, color="#4c78a8", hatch=hatches[k],
                       edgecolor="black", label=label)
            else:
                ax.bar(pos, series(group).reindex(xs).to_numpy(), width, hatch=hatches[k],
                       edgecolor="black", label=label)
        if number == 7:
            ax.bar([0], [series("ICE gas CO2 (Bt)").iloc[0]], 0.6, color="#bdbdbd",
                   edgecolor="black")
            ax.bar([len(xs) - 1], [series("EV grid CO2 (Bt)").iloc[0]], 0.6, color="#4c78a8",
                   edgecolor="black")
        if dots:
            target = ax.twinx() if dot_label else ax
            for k, name in enumerate(dots):
                pos = np.arange(len(xs)) - 0.4 + width * (k + 0.5) if len(dots) > 1 \
                    else np.arange(len(xs))
                label = name.removeprefix("dots: ").split(" (")[0]
                target.plot(pos, series(name).reindex(xs).to_numpy(), "ko", markersize=4,
                            label=f"dots (right axis): {label}" if dot_label and k == 0
                            else (f"dots: {label}" if k == 0 else None))
            if dot_label:
                target.set_ylabel(dot_label)
                target.set_ylim(bottom=0)
        if log:
            ax.set_yscale("log")
        ax.set_xticks(np.arange(len(xs)), [str(x) for x in xs])
        ax.set_xlabel("EV range (miles)")
        ax.set_ylabel(ylabel)
        ax.set_title(f"Figure {number}. {title}")
        # Legend below the axes, so it never covers a bar.
        handles, labels = ax.get_legend_handles_labels()
        if dots and dot_label:
            more = target.get_legend_handles_labels()
            handles, labels = handles + more[0], labels + more[1]
        fig.legend(handles, labels, loc="lower center", ncols=min(len(labels), 5), fontsize=8)
        fig.tight_layout(rect=(0, 0.07, 1, 1))
        path = fig_dir / f"fig{number:02d}.png"
        fig.savefig(path, dpi=200)
        plt.close(fig)
        written.append(path)
    return written


def write_figure1(fig1: pd.DataFrame, fig_dir: Path) -> Path:
    """Figure 1 from costs.figure1_data: CO2 bars, VMT dots on a second axis."""
    fig_dir.mkdir(parents=True, exist_ok=True)
    co2 = fig1[fig1.series == "CO2 (Bt)"].set_index("x")["y"]
    vmt = fig1[fig1.series == "VMT (T)"].set_index("x")["y"].reindex(co2.index)
    xs = np.arange(len(co2))
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar(xs, co2.to_numpy(), 0.6, color="#9ecae1", edgecolor="black", label="CO2 (bars)")
    ax.set_ylabel("CO2 (billion t, 2022)")
    twin = ax.twinx()
    twin.plot(xs, vmt.to_numpy(), "ko", label="VMT (dots, right axis)")
    twin.set_ylabel("VMT (trillion miles)")
    twin.set_ylim(bottom=0)
    ax.set_xticks(xs, list(co2.index), rotation=20, ha="right")
    ax.set_title("Figure 1. Emissions and VMT by transport mode (2022)\n"
                 "rail, watercraft, aircraft, non-transport and pipeline VMT are the "
                 "published placeholders")
    handles = ax.get_legend_handles_labels()[0] + twin.get_legend_handles_labels()[0]
    fig.legend(handles, [h.get_label() for h in handles], loc="lower center", ncols=2,
               fontsize=8)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    path = fig_dir / "fig01.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def write_figure4(fig4: pd.DataFrame, fig_dir: Path) -> Path:
    """Figure 4 from costs.figure4_data: a grid of one household's week, rows by charges
    per week and columns by range. Bars are each day's EV (blue) and gas (grey, hatched)
    miles; dots are the battery range at the start of the day."""
    fig_dir.mkdir(parents=True, exist_ok=True)
    keys = fig4.series.str.extract(r"^(\d+)/week R=(\d+) (.*)$")
    fig4 = fig4.assign(cpw=keys[0].astype(int), r=keys[1].astype(int), what=keys[2])
    cpws = list(dict.fromkeys(fig4.cpw))
    ranges = list(dict.fromkeys(fig4.r))
    days = list(dict.fromkeys(fig4.x))
    xs = np.arange(len(days))
    fig, axes = plt.subplots(len(cpws), len(ranges), figsize=(16, 13), sharex=True,
                             sharey=True)
    for i, cpw in enumerate(cpws):
        for j, r in enumerate(ranges):
            ax = axes[i, j]
            panel = fig4[(fig4.cpw == cpw) & (fig4.r == r)]

            def get(what, panel=panel):
                return panel[panel.what == what].set_index("x")["y"].reindex(days).to_numpy()

            ev, gas = get("EV miles"), get("gas miles")
            ax.bar(xs, ev, 0.75, color="#4c78a8", edgecolor="black", label="EV miles")
            ax.bar(xs, gas, 0.75, bottom=ev, color="#bdbdbd", hatch="//", edgecolor="black",
                   label="gas miles")
            ax.plot(xs, get("start-of-day range"), "ko-", markersize=4,
                    label="range at start of day")
            ax.set_ylim(0, 200)
            if i == 0:
                ax.set_title(f"EV range = {r} mi")
            if j == 0:
                ax.set_ylabel(f"{cpw} charges/week\nmiles")
            ax.set_xticks(xs, days)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncols=3)
    fig.suptitle("Figure 4. One household's week by EV range and charging frequency\n"
                 "(weekly profile recovered from the workbook; see config weekly_profile)")
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    path = fig_dir / "fig04.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
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
