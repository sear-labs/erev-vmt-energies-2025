"""Every number the paper states in prose, asserted against a real run.

This is the test that matters. The standard's Part 6 requires that a specific
number in the prose came from running the code, and the only durable way to
keep that true is to make the claim executable. If a refactor moves 73.3% to
73.9%, this goes red and names the sentence in the paper that is now wrong.

Reference:
  Patil, H.V., Kumbhar, A.A. & Jones, E.C., Jr. "Contributions of Extended-Range
  Electric Vehicles (EREVs) to Electrified Miles, Emissions and Transportation
  Cost Reduction." Energies 2025, 18, 6448. https://doi.org/10.3390/en18246448
"""

from __future__ import annotations

import pytest

from erev_vmtalloc import metrics
from erev_vmtalloc.allocation import split_vmt

# Abstract: "EREVs with a 50-mile range (13.7 kWh battery) could electrify 73.3%
# of national VMT, while 150-mile range EVs could electrify 86.8%".
# The paper reports one decimal place, so the tolerance is half of that.
PUBLISHED_EV_SHARE_PCT = {50: 73.3, 150: 86.8}
SHARE_TOLERANCE_PCT = 0.05


@pytest.mark.parametrize("electric_range,published", PUBLISHED_EV_SHARE_PCT.items())
def test_published_ev_share(fitted, config, electric_range, published):
    split = split_vmt(fitted, electric_range, round_trip=config.round_trip)
    assert split.ev_share_pct == pytest.approx(published, abs=SHARE_TOLERANCE_PCT), (
        f"Paper states {published}% of VMT electrified at {electric_range} miles; "
        f"this run produces {split.ev_share_pct:.2f}%."
    )


def test_ev_share_rises_with_range(fitted, config):
    """"Diminishing returns at higher ranges" requires the curve to rise at all."""
    shares = [
        split_vmt(fitted, r, round_trip=config.round_trip).ev_share_pct
        for r in config.ranges
    ]
    assert shares == sorted(shares), f"EV share is not monotone in range: {shares}"


def test_diminishing_returns(fitted, config):
    """The paper's central claim: each extra 25 miles buys less than the last."""
    shares = [
        split_vmt(fitted, r, round_trip=config.round_trip).ev_share_pct
        for r in config.ranges
    ]
    gains = [b - a for a, b in zip(shares, shares[1:], strict=False)]
    first_gain_per_mile = gains[0] / (config.ranges[1] - config.ranges[0])
    last_gain_per_mile = gains[-1] / (config.ranges[-1] - config.ranges[-2])
    assert last_gain_per_mile < first_gain_per_mile, (
        "Paper claims diminishing returns, but the last range step gains more "
        f"per mile ({last_gain_per_mile:.4f}) than the first ({first_gain_per_mile:.4f})."
    )


def test_battery_size_at_50_miles_diverges_from_paper(fitted, config):
    """The abstract's "13.7 kWh" does not follow from the configured efficiency.

    range / eta = 50 / 3.6 = 13.89 kWh, not 13.7. 13.7 implies eta = 3.65 mi/kWh.
    This test pins what the CODE does, and exists so the divergence cannot be
    quietly "fixed" in either direction without a decision. See README,
    "Stated residuals".
    """
    computed = metrics.pack_kwh(50, config["battery"]["eta_mi_per_kwh"])
    assert computed == pytest.approx(13.889, abs=0.001)
    assert abs(computed - 13.7) > 0.1, (
        "The code now agrees with the paper's 13.7 kWh. If that was deliberate, "
        "update this test and the README residual; if not, it is a regression."
    )
