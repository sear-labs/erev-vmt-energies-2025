"""Domain invariants: what must be true of any correct output.

These do not check that the model is right. They check that it is not
arithmetically impossible -- miles that appear or vanish, shares outside
[0, 100], a normalization that did not normalize. Part 1 rule 6 asks for
exactly this, and it is what catches a refactor that loses a bin.
"""

from __future__ import annotations

import numpy as np
import pytest

from erev_vmtalloc import metrics, scenarios
from erev_vmtalloc.allocation import ev_ratio_per_bin, split_vmt


def test_ev_plus_gas_equals_total(fitted, config):
    """No mile is created or destroyed by the allocation."""
    total_billion = fitted.annual_vmt_billion
    for r in config.ranges:
        split = split_vmt(fitted, r, round_trip=config.round_trip)
        assert split.ev_billion + split.gas_billion == pytest.approx(
            total_billion, rel=1e-9
        ), f"At R={r}, EV + gas != total VMT"


def test_shares_are_percentages(fitted, config):
    for r in config.ranges:
        split = split_vmt(fitted, r, round_trip=config.round_trip)
        assert 0.0 <= split.ev_share_pct <= 100.0
        assert split.ev_billion >= 0.0
        assert split.gas_billion >= 0.0


def test_normalization_hits_fhwa_exactly(fitted):
    """Post-normalization every month matches its FHWA target."""
    assert np.abs(fitted.monthly_error_pct(prenorm=False)).max() < 1e-9


def test_normalization_preserves_annual_total(fitted):
    assert fitted.annual_vmt_billion == pytest.approx(
        float(fitted.fhwa_billion.sum()), rel=1e-9
    )


def test_ev_ratio_bounded(fitted, config):
    for r in config.ranges:
        ratio = ev_ratio_per_bin(r, fitted.mean_distance, round_trip=config.round_trip)
        assert np.all(ratio >= 0.0) and np.all(ratio <= 1.0)


def test_round_trip_is_stricter_than_one_way(fitted, config):
    """Requiring the battery to cover out-and-back can never electrify more."""
    for r in config.ranges:
        round_trip = split_vmt(fitted, r, round_trip=True)
        one_way = split_vmt(fitted, r, round_trip=False)
        assert round_trip.ev_billion <= one_way.ev_billion + 1e-9


def test_fitted_distances_lie_within_their_bins(fitted, config):
    for label, distance in zip(fitted.bins, fitted.mean_distance, strict=True):
        lo, hi = config["bin_bounds"][label]
        assert lo - 1e-9 <= distance <= hi + 1e-9, (
            f"Bin {label}: fitted mean {distance} is outside its bounds [{lo}, {hi}]"
        )


def test_fit_is_pinned_at_lower_bounds(fitted, config):
    """The fit is degenerate: every bin sits on its own lower bound.

    This is not an invariant of a correct model -- it is a measured property of
    THIS one, pinned so it cannot change silently. The bounded least squares has
    no interior optimum: it wants smaller distances than the bins permit and is
    clamped everywhere. So the "calculated average bin distance" column of the
    paper's Table 1 is the configured lower bounds, and the EV share reduces to
    min(1, R / 2*lower_bound) per bin.

    If a change makes any bin leave its floor, the fit has started doing
    something, and that is a result worth noticing rather than a test to relax.
    See README, "Stated residuals".
    """
    floors = np.array([config["bin_bounds"][b][0] for b in fitted.bins], float)
    assert np.allclose(fitted.mean_distance, floors, atol=1e-6), (
        "Fitted distances are no longer all at their lower bounds:\n"
        f"  fitted: {np.round(fitted.mean_distance, 4)}\n"
        f"  floors: {floors}"
    )


def test_scenario_budget_never_increases_ev_miles(fitted, config):
    """A charging cap can only remove electric miles, never add them."""
    acs = {}
    n_vehicles = metrics.fleet_size(
        fitted.annual_vmt_billion, config["fleet"]["avg_driver_miles"]
    )
    for scenario in ("Low", "Normal", "More"):
        for r in config.ranges:
            budget = scenarios.annual_ev_budget_miles(scenario, r, n_vehicles, acs, config)
            capped = split_vmt(
                fitted, r, round_trip=config.round_trip, ev_budget_miles=budget
            )
            base = split_vmt(fitted, r, round_trip=config.round_trip)
            assert capped.ev_billion <= base.ev_billion + 1e-9, (
                f"{scenario} at R={r} produced MORE electric miles than the "
                "uncapped base case."
            )


def test_more_charging_never_reduces_ev_miles(fitted, config):
    """Low <= Normal <= More at every range."""
    acs = {}
    n_vehicles = metrics.fleet_size(
        fitted.annual_vmt_billion, config["fleet"]["avg_driver_miles"]
    )

    def ev_at(scenario, r):
        budget = scenarios.annual_ev_budget_miles(scenario, r, n_vehicles, acs, config)
        return split_vmt(
            fitted, r, round_trip=config.round_trip, ev_budget_miles=budget
        ).ev_billion

    for r in config.ranges:
        low, normal, more = (ev_at(s, r) for s in ("Low", "Normal", "More"))
        assert low <= normal + 1e-9 <= more + 1e-9, (
            f"At R={r}: Low={low:.1f} Normal={normal:.1f} More={more:.1f} "
            "are not ordered by charging frequency."
        )
