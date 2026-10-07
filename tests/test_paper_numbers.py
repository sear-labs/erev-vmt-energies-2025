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

import math
from pathlib import Path

import pytest

from erev_vmtalloc import costs, metrics, verify
from erev_vmtalloc.allocation import split_vmt

ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "tests" / "fixtures" / "article"
RAW = ROOT / "data" / "raw"

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


# ===========================================================================
# Every printed cell of Tables 1-3 and 5-6
# ===========================================================================
# The comparison itself lives in erev_vmtalloc.verify, so this suite and
# notebooks/verify.ipynb run the same check. A printed value must equal the package's
# number rounded to the printed precision; 19 cells in Tables 2-3 that were truncated
# in print are listed by name in verify.TRUNCATED.


@pytest.mark.parametrize("name", ["table1", "table2", "table3", "table5", "table6"])
def test_every_printed_cell(fitted, config, name):
    result = verify.check(name, verify.cells(name, fitted, config, ARTICLE))
    print(result)
    assert result.rounded + result.truncated > 0, f"{name}: compared nothing"
    assert not result.misses, "\n".join(result.misses)


def test_the_truncation_list_names_real_cells(fitted, config):
    """Every entry in verify.TRUNCATED must be a cell the comparison actually reaches."""
    reached = {(n, row, col) for n in ("table2", "table3")
               for row, col, _, _ in verify.cells(n, fitted, config, ARTICLE)}
    assert verify.TRUNCATED <= reached, sorted(verify.TRUNCATED - reached)


@pytest.fixture(scope="module")
def scen(fitted, config):
    return costs.scenario_table(fitted, config)


@pytest.fixture(scope="module")
def chg(fitted, config):
    return costs.charging_table(fitted, config, RAW)


# ===========================================================================
# Sentences in the prose that reproduce
# ===========================================================================

def _row(scen, scenario, vehicle):
    return scen[(scen["Scenario"] == scenario) & (scen["Vehicle Type"] == vehicle)].iloc[0]


def _avg(scen, r):
    return _row(scen, "Average", costs.ldv_label(r))


def test_prose_numbers_reproduce(fitted, config):
    rows = verify.prose_numbers(fitted, config)
    misses = []
    for where, quote, ours, printed in rows:
        value, d = verify.parse(printed)
        ok = verify.rounds_to(float(ours), value, d)
        print(f"{'ok  ' if ok else 'MISS'} {where:<11} {quote:<42} ours {float(ours):.6g}")
        if not ok:
            misses.append(f"{where}: '{quote}' printed {printed}, ours {float(ours)!r}")
    assert len(rows) == 31
    assert not misses, "\n".join(misses)


def test_section_4_7_thresholds(scen):
    """4.7: at 800 g/kWh, or 2.8 mi/kWh, or above 37 mpg, worst-case EREVs emit more.

    The worst case's electric mile (714 g/kWh at 2.9 mi/kWh) emits just less than its
    gasoline mile (8,888 g/gal at 36 mpg). Each of the three changes flips that.
    """
    worst = _row(scen, "Worst", costs.ICE)
    gas = worst["kg CO2 / gallon"] * 1000 / worst["MPG"]
    electric = worst["Grid g CO2 / kWh"] / worst["mi / kWh"]
    print(f"worst case: gasoline {gas:.1f} g/mi, electric {electric:.1f} g/mi")
    assert electric < gas, "the worst case already has electric above gasoline"
    assert 800 / worst["mi / kWh"] > gas
    assert worst["Grid g CO2 / kWh"] / 2.8 > gas
    assert worst["kg CO2 / gallon"] * 1000 / 37 < electric


def test_figure_12_mpge():
    """4.8: "very inefficient EV (2.9 mi/kWh, 97.7 mpge)", at 33.7 kWh per gallon."""
    assert round(2.9 * 33.7, 1) == 97.7


# ===========================================================================
# Sentences and cells that do NOT reproduce, pinned
# ===========================================================================
# Each test below pins a disagreement between the article and its own computation.
# It goes red if the code moves so that the disagreement disappears, which is a change
# somebody must decide on, not one that should happen quietly. Each is listed in the
# README under "What reproduces, and what doesn't".

def test_summary_150_mile_capex_per_kg_is_ten_times_the_table(scen):
    """Summary: "to 1.82 USD/kg CO2 (150 mile)". Table 6 and the conclusions say 0.18."""
    ours = _avg(scen, 150)["$ CAPEX / kg CO2"]
    assert round(ours, 3) == 0.182
    assert round(ours * 10, 2) == 1.82


def test_summary_679_mt_is_a_truncation(scen):
    """Summary: "679 Mt (150 mi)". 679.73 rounds to 680, which the conclusions print."""
    ours = _avg(scen, 150)["CO2 Saved (Mt CO2)"]
    assert math.floor(ours) == 679 and round(ours) == 680


def test_text_and_tables_use_two_cost_models(fitted, config, scen):
    """4.3's $0.161/mi and $712/t, and Table 6's $0.017/mi and $72/t, describe one case.

    They differ about tenfold: per year against over a ten-year life, on a 241.8 M
    fleet against 257.7 M, at 26.2 mpg and 387 g/kWh against 26.4 and 348.
    """
    old = metrics.summarize([split_vmt(fitted, 50, round_trip=config.round_trip)], config)
    new = _avg(scen, 50)
    ratio = old["$ / electric mile"].iloc[0] / new["$ CAPEX / EV Mile"]
    print(f"$/electric mile at 50 mi: text {old['$ / electric mile'].iloc[0]:.3f}, "
          f"Table 6 {new['$ CAPEX / EV Mile']:.3f}, ratio {ratio:.1f}")
    assert 8 < ratio < 12


def test_table4_vehicle_count_is_not_the_one_used(config, scen):
    """Table 4 prints "Vehicle Count 286.1 M"; Tables 5-6 used 257.7 M (2022 LDVs)."""
    assert round(config["paper_scenarios"]["vehicles"] / 1e6, 1) == 257.7
    # Table 6's Average 50-mile capacity, 3.6 TWh, needs 257.7 M; 286.1 M gives 4.0.
    assert round(_avg(scen, 50)["Installed Battery (TWh)"], 1) == 3.6
    assert round(_avg(scen, 50)["Battery Size (kWh)"] * 286.1e6 / 1e9, 1) == 4.0


def test_table4_kg_per_gallon_is_not_the_one_used(scen):
    """Table 4 prints 8.887 kg/gal; Table 5's 805.55 Mt needs 8.888."""
    worst_ice = _row(scen, "Worst", costs.ICE)
    assert worst_ice["kg CO2 / gallon"] == 8.888
    assert round(worst_ice["Gallons (B)"] * 8.888, 2) == 805.55
    assert round(worst_ice["Gallons (B)"] * 8.887, 2) != 805.55


def test_table4_prints_three_rows_in_the_reverse_order(config):
    """Table 4's heading says Worst/Average/Best; fuel economy, grid intensity and
    electricity price are printed Best/Average/Worst."""
    s = config["paper_scenarios"]["scenarios"]
    printed = verify.printed_table(ARTICLE, "table4").set_index("parameter")["printed_value"]
    assert printed["Average Fuel Economy"].startswith("18/26.4/36")
    assert (s["Worst"]["mpg"], s["Best"]["mpg"]) == (36.0, 18.0)
    assert printed["U.S. Grid CO2 Intensity (2023)"].startswith("125/348/714")
    assert (s["Worst"]["grid_g_per_kwh"], s["Best"]["grid_g_per_kwh"]) == (714.0, 125.0)
    assert printed["Average Retail Electricity Price (U.S.)"].startswith("USD 0.15/")
    assert (s["Worst"]["elec_usd_per_kwh"], s["Best"]["elec_usd_per_kwh"]) == (0.40, 0.15)


def test_table6_average_ev_row_uses_the_best_case_electricity_price(scen):
    """Table 6, Average, EV: $OPEX 135.95 is 906.3 TWh at $0.15/kWh, not $0.25."""
    ev = _row(scen, "Average", costs.EV)
    assert ev["$ / kWh"] == 0.15
    assert round(ev["OPEX ($B)"], 2) == 135.95
    assert round(ev["Electricity (TWh)"] * 0.25, 2) == 226.58


def test_daily_charging_runs_four_percent_above_the_average_scenario(fitted, scen, chg):
    """4.6, on Figure 5: the scenarios are "similar to the 7-day-a-week charging
    frequency VMT ratio ... but with slightly more electric VMT".

    The ratio is identical and the scenarios have LESS electric VMT. The charging
    figures stand on Table 1's printed total, 3,392.5 B, while the tables and the
    scenario figures use FHWA's 3,262.8 B. Of the 3.97%, 3.74 points are the fit
    before normalisation and 0.22 the 0-1 mile bin's display rounding.
    """
    seven = chg[chg["Charges / week"] == 7].set_index("Vehicle Type")
    total_chg = float(seven["VMT (B)"].iloc[0])
    excess = total_chg / fitted.annual_vmt_billion - 1
    assert round(total_chg, 3) == 3392.497
    assert round(fitted.annual_vmt_billion, 1) == 3262.8
    for vehicle, row in seven.iterrows():
        r = int(vehicle.split("(")[1].split("-")[0])
        assert row["% Electric"] == pytest.approx(_avg(scen, r)["% Electric"], rel=1e-5)
        assert row["Electric VMT (B)"] / _avg(scen, r)["Electric VMT (B)"] - 1 == pytest.approx(
            excess, abs=1e-5)
    print(f"7-a-week electric VMT exceeds the Average scenario by {100 * excess:.2f}% at "
          f"every range (25 mi: {seven['Electric VMT (B)'].iloc[0]:.1f} B against "
          f"{_avg(scen, 25)['Electric VMT (B)']:.1f} B)")
    assert 0.039 < excess < 0.040


def test_up_to_75_percent_loss_does_not_regenerate(fitted, config, chg):
    """Conclusions: charging fewer than five times a week "can lose up to 75% of
    potential electrified miles".

    Two models in the paper compute that loss, and neither reaches 75%. Nationally
    (the charging-frequency figures), the largest loss, two charges a week against
    seven at 25 miles, is 39%. In Figure 4's weekly simulation, with the recovered
    profile, it is 57%. A search of every charging quantity found 75% only in things
    that are not lost electric miles: gas use rising 75% (5 a week, 125 miles), and
    CAPEX per ton rising 74% (2 a week, 25 miles). Pinned as not regenerating.
    """
    ev = chg.pivot(index="Vehicle Type", columns="Charges / week", values="Electric VMT (B)")
    national = float((1 - ev[[3, 2]].min(axis=1) / ev[7]).max())

    wp = config["paper_scenarios"]["weekly_profile"]
    daily = costs.weekly_profile(fitted, config)
    weekly = 0.0
    for r in wp["ranges"]:
        full = costs.simulate_week(r, daily, wp["charge_nights"][7])["ev_miles"].sum()
        for cpw in (3, 2):
            got = costs.simulate_week(r, daily, wp["charge_nights"][cpw])["ev_miles"].sum()
            weekly = max(weekly, 1 - got / full)
    print(f"largest loss below five charges a week: national {100 * national:.1f}%, "
          f"Figure 4's weekly simulation {100 * weekly:.1f}%")
    assert 0.35 < national < 0.45
    assert 0.50 < weekly < 0.60
