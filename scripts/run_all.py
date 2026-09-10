"""Reproduce every table and figure in the paper. One command, no network.

    python scripts/run_all.py

Reads the frozen snapshots in data/raw/, writes results/tables/ and
results/figures/. Inputs are never written to. If a snapshot is missing the
run stops and says how to fetch it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from erev_vmtalloc import metrics, report, scenarios, sources  # noqa: E402
from erev_vmtalloc.allocation import fit_bin_distances, split_vmt  # noqa: E402
from erev_vmtalloc.config import load_config  # noqa: E402


def build(config, raw_dir: Path):
    """Stage 1 and 2: fit bin distances, then hold the fitted object."""
    trips = sources.load_bts_trips(raw_dir, config.year)
    fhwa = sources.load_fhwa_vmt(raw_dir, config.year)
    return fit_bin_distances(
        trips,
        fhwa,
        config["bin_bounds"],
        normalize_to_fhwa=config.normalize_to_fhwa,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(REPO_ROOT / "config" / "base.yaml"))
    parser.add_argument("--results", default=str(REPO_ROOT / "results"))
    args = parser.parse_args()

    config = load_config(args.config)
    raw_dir = REPO_ROOT / "data" / "raw"
    results = Path(args.results)
    tables_dir = results / "tables"
    figures_dir = results / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)

    print(f"Config:  {config.path}")
    print(f"Inputs:  {raw_dir}")
    print(f"Outputs: {results}\n")

    fitted = build(config, raw_dir)

    # --- Stage 1 reporting -------------------------------------------------
    monthly = report.monthly_fit_table(fitted)
    report.write_csv(monthly, tables_dir / "monthly_fit.csv")
    worst_pre = float(np.abs(fitted.monthly_error_pct(prenorm=True)).max())
    print(f"Fit: max |monthly error| pre-normalization = {worst_pre:.2f}%")
    if config.normalize_to_fhwa:
        worst_post = float(np.abs(fitted.monthly_error_pct(prenorm=False)).max())
        print(f"     max |monthly error| post-normalization = {worst_post:.6f}%")

    month_tbl = report.month_table(fitted, config.month_to_show)
    report.write_csv(month_tbl, tables_dir / f"table1_month_{config.month_to_show:02d}.csv")

    annual_tbl = report.annual_table(fitted)
    report.write_csv(annual_tbl, tables_dir / "table1_annual.csv")
    print(f"     annual VMT (normalized) = {fitted.annual_vmt_billion:.1f} B miles\n")

    # --- Stage 2: base case ------------------------------------------------
    base_splits = [
        split_vmt(fitted, r, round_trip=config.round_trip, scenario="Base_EachTrip")
        for r in config.ranges
    ]
    summary = metrics.summarize(base_splits, config)
    report.write_csv(summary, tables_dir / "range_summary_base.csv")

    print("Base case (round-trip constraint, unlimited charging):")
    for split in base_splits:
        print(
            f"  R={split.electric_range:>5.0f} mi   "
            f"EV share {split.ev_share_pct:6.2f}%   "
            f"EV {split.ev_billion:8.1f} B   gas {split.gas_billion:7.1f} B"
        )

    for split in base_splits:
        report.write_csv(
            split.per_bin, tables_dir / f"per_bin_base_R{int(split.electric_range)}.csv"
        )

    # --- Stage 2b: charging-frequency scenarios ----------------------------
    # Only the corrected acs_b25032 path reads the ACS snapshot; the default
    # published_fallback path does not, which is what lets a clean clone with
    # no Census API key still reproduce the paper.
    acs = (
        sources.load_acs_units(raw_dir)
        if config["charging"]["weights_source"] == "acs_b25032"
        else {}
    )
    print(f"Charging weights source: {config['charging']['weights_source']}")
    n_vehicles = metrics.fleet_size(
        fitted.annual_vmt_billion, config["fleet"]["avg_driver_miles"]
    )
    print(f"\nFleet size implied by VMT / avg annual miles: {n_vehicles / 1e6:.1f} M vehicles")

    scenario_rows = []
    for scenario in config["scenarios"]:
        if scenario == "Base_EachTrip":
            splits = base_splits
        else:
            cpw = scenarios.charges_per_week(scenario, acs, config)
            print(f"\nScenario {scenario}: fleet-average {cpw:.3f} charges/week")
            splits = []
            for r in config.ranges:
                budget = scenarios.annual_ev_budget_miles(scenario, r, n_vehicles, acs, config)
                splits.append(
                    split_vmt(
                        fitted,
                        r,
                        round_trip=config.round_trip,
                        scenario=scenario,
                        ev_budget_miles=budget,
                    )
                )
            for split, base in zip(splits, base_splits, strict=True):
                binds = split.ev_billion < base.ev_billion - 1e-6
                print(
                    f"  R={split.electric_range:>5.0f} mi   "
                    f"EV share {split.ev_share_pct:6.2f}%   "
                    f"{'budget binds' if binds else 'budget slack'}"
                )

        table = metrics.summarize(splits, config)
        report.write_csv(table, tables_dir / f"range_summary_{scenario}.csv")
        scenario_rows.append(table)

    report.write_csv(
        pd.concat(scenario_rows, ignore_index=True),
        tables_dir / "range_summary_all_scenarios.csv",
    )

    # --- Figures -----------------------------------------------------------
    written = report.write_figures(summary, figures_dir)
    print(f"\nWrote {len(list(tables_dir.glob('*.csv')))} tables to {tables_dir}")
    print(f"Wrote {len(written)} figures to {figures_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
