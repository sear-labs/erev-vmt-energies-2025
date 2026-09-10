"""The model: fit per-bin mean distances, then split VMT into electric and gas.

Two stages, in one direction.

1. `fit_bin_distances` chooses one vector of average trip distances -- one entry
   per BTS distance bin, the same vector for all twelve months -- by bounded
   least squares against FHWA monthly VMT. Each entry is constrained to lie
   inside the bin it describes, which is what stops the fit from explaining a
   monthly total with a 4-mile average in the 100-250 bin.

2. `split_vmt` allocates each bin's VMT to electric or gasoline by comparing the
   bin's mean distance against the vehicle's electric range.

Numerics here reproduce the published notebook exactly; see
tests/test_paper_numbers.py, which asserts the two headline percentages.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear


@dataclass(frozen=True)
class FittedVmt:
    """Output of stage 1: the fitted distances and the VMT they imply.

    Attributes:
        bins: bin labels, in increasing distance order.
        months: the months present, in order.
        mean_distance: fitted average trip distance per bin, in miles.
        trips: (months x bins) trip counts, as fetched.
        vmt_miles: (months x bins) VMT in miles, after optional normalization.
        vmt_miles_prenorm: the same, before normalization.
        fhwa_billion: FHWA target per month, in billions of miles.
    """

    bins: list[str]
    months: list[int]
    mean_distance: np.ndarray
    trips: np.ndarray
    vmt_miles: np.ndarray
    vmt_miles_prenorm: np.ndarray
    fhwa_billion: np.ndarray

    @property
    def annual_trips_billion(self) -> np.ndarray:
        return self.trips.sum(axis=0) / 1e9

    @property
    def annual_vmt_billion_per_bin(self) -> np.ndarray:
        return self.vmt_miles.sum(axis=0) / 1e9

    @property
    def annual_vmt_billion(self) -> float:
        return float(self.vmt_miles.sum() / 1e9)

    def monthly_error_pct(self, *, prenorm: bool) -> np.ndarray:
        source = self.vmt_miles_prenorm if prenorm else self.vmt_miles
        modelled = source.sum(axis=1) / 1e9
        return 100.0 * (modelled - self.fhwa_billion) / self.fhwa_billion


def fit_bin_distances(
    trips: pd.DataFrame,
    fhwa_billion_by_month: dict[int, float],
    bin_bounds: dict[str, list[float]],
    *,
    normalize_to_fhwa: bool = True,
) -> FittedVmt:
    """Solve for one set of per-bin mean distances across all months.

    Args:
        trips: 12-row frame, a `month` column plus one column per bin.
        fhwa_billion_by_month: FHWA VMT targets, billions of miles.
        bin_bounds: {bin label: [lo, hi]} in miles, the feasible mean per bin.
        normalize_to_fhwa: rescale each month's VMT to hit its FHWA total
            exactly. Does not refit the distances.
    """
    bins = [c for c in trips.columns if c != "month"]
    months = [int(m) for m in trips["month"].tolist()]

    missing_bounds = [b for b in bins if b not in bin_bounds]
    if missing_bounds:
        raise ValueError(f"No bin_bounds configured for bins: {missing_bounds}")
    missing_targets = [m for m in months if m not in fhwa_billion_by_month]
    if missing_targets:
        raise ValueError(f"No FHWA target for months: {missing_targets}")

    trip_matrix = trips[bins].to_numpy(float)
    if not np.isfinite(trip_matrix).all():
        raise ValueError("Trip counts contain NaN or inf; the input snapshot is incomplete.")

    fhwa_billion = np.array([fhwa_billion_by_month[m] for m in months], float)
    target_miles = fhwa_billion * 1e9

    lo = np.array([bin_bounds[b][0] for b in bins], float)
    hi = np.array([bin_bounds[b][1] for b in bins], float)

    solution = lsq_linear(trip_matrix, target_miles, bounds=(lo, hi), lsmr_tol="auto", verbose=0)
    mean_distance = solution.x

    vmt_prenorm = trip_matrix * mean_distance.reshape(1, -1)
    vmt = vmt_prenorm.copy()
    if normalize_to_fhwa:
        modelled_billion = vmt.sum(axis=1) / 1e9
        scale = (fhwa_billion / np.maximum(modelled_billion, 1e-12)).reshape(-1, 1)
        vmt = vmt * scale

    return FittedVmt(
        bins=bins,
        months=months,
        mean_distance=mean_distance,
        trips=trip_matrix,
        vmt_miles=vmt,
        vmt_miles_prenorm=vmt_prenorm,
        fhwa_billion=fhwa_billion,
    )


def ev_ratio_per_bin(
    electric_range: float, mean_distance: np.ndarray, *, round_trip: bool = True
) -> np.ndarray:
    """Fraction of a bin's miles that can be driven electrically.

    One-way:    min(1, R / d)
    Round-trip: min(1, R / 2d)  -- the base case: the battery must cover the
                trip out and back, because there is no charging at the far end.
    """
    distance = np.asarray(mean_distance, float)
    factor = 2.0 if round_trip else 1.0
    return np.minimum(1.0, electric_range / np.maximum(factor * distance, 1e-9))


@dataclass(frozen=True)
class Split:
    """The electric/gasoline allocation at one range under one scenario."""

    electric_range: float
    scenario: str
    ev_billion: float
    gas_billion: float
    ev_share_pct: float
    per_bin: pd.DataFrame


def split_vmt(
    fitted: FittedVmt,
    electric_range: float,
    *,
    round_trip: bool = True,
    scenario: str = "Base_EachTrip",
    ev_budget_miles: float | None = None,
) -> Split:
    """Allocate fitted VMT to electric or gasoline at one electric range.

    Args:
        ev_budget_miles: annual fleet-wide cap on electric miles, imposed by a
            charging-frequency scenario. When the unconstrained allocation
            already fits under the cap, the cap does nothing and the base
            result is returned unchanged.
    """
    ratio = ev_ratio_per_bin(electric_range, fitted.mean_distance, round_trip=round_trip)
    ev_per_bin = (fitted.vmt_miles * ratio.reshape(1, -1)).sum(axis=0)
    vmt_per_bin = fitted.vmt_miles.sum(axis=0)

    if ev_budget_miles is not None and ev_per_bin.sum() > ev_budget_miles:
        # Budget binds: scale electric miles down proportionally across bins.
        ev_per_bin = ev_per_bin * (ev_budget_miles / ev_per_bin.sum())

    gas_per_bin = vmt_per_bin - ev_per_bin
    total = vmt_per_bin.sum()

    per_bin = pd.DataFrame(
        {
            "Trip Distance Bin (miles)": fitted.bins,
            "Average Distance (miles)": np.round(fitted.mean_distance, 1),
            "Trips (B/year)": np.round(fitted.annual_trips_billion, 3),
            "VMT (B/year)": np.round(vmt_per_bin / 1e9, 3),
            "EV VMT (B/year)": np.round(ev_per_bin / 1e9, 3),
            "Gas VMT (B/year)": np.round(gas_per_bin / 1e9, 3),
            "EV% in bin": np.round(100 * ev_per_bin / np.maximum(vmt_per_bin, 1e-12), 1),
        }
    )

    return Split(
        electric_range=float(electric_range),
        scenario=scenario,
        ev_billion=float(ev_per_bin.sum() / 1e9),
        gas_billion=float(gas_per_bin.sum() / 1e9),
        ev_share_pct=float(100 * ev_per_bin.sum() / max(total, 1e-12)),
        per_bin=per_bin,
    )
