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

import pandas as pd
import pytest

from erev_vmtalloc import costs, metrics, report
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
#
# The article's tables are in tests/fixtures/article/, as printed. A printed value with
# d decimals is reproduced when the package's full-precision number ROUNDS to it.
#
# Nineteen cells in Tables 2 and 3 do not round to the printed value but TRUNCATE to it
# (January's modelled VMT is 278.367; the article prints 278.36). They are listed by
# name below. Each must truncate to its printed value and must NOT round to it, so the
# list cannot quietly go stale in either direction. Every other cell must round.

TRUNCATED = {
    ("table2", "1", "model_vmt_b"), ("table2", "2", "model_vmt_b"), ("table2", "2", "error_pct"),
    ("table2", "7", "model_vmt_b"), ("table2", "11", "model_vmt_b"),
    ("table2", "11", "error_pct"), ("table2", "12", "model_vmt_b"),
    ("table3", "0-1", "vmt_b_yr"), ("table3", "0-1", "ev_vmt_b_yr"),
    ("table3", "3-5", "vmt_b_yr"), ("table3", "3-5", "ev_vmt_b_yr"),
    ("table3", "5-10", "trips_b_yr"), ("table3", "25-50", "trips_b_yr"),
    ("table3", "50-100", "trips_b_yr"), ("table3", "50-100", "vmt_b_yr"),
    ("table3", "100-250", "trips_b_yr"), ("table3", "100-250", "vmt_b_yr"),
    ("table3", "250-500", "gas_vmt_b_yr"), ("table3", "500+", "vmt_b_yr"),
}


def _parse(printed: str):
    """'$ 57.47' -> (57.47, 2); '59.4%' -> (59.4, 1); 'N/A' and '$-' -> (None, 0)."""
    text = str(printed).replace("$", "").replace("%", "").replace(",", "").strip()
    if text in ("N/A", "-", ""):
        return None, 0
    return float(text), len(text.split(".")[1]) if "." in text else 0


def _rounds_to(ours: float, printed: float, decimals: int) -> bool:
    return abs(ours - printed) <= 0.5 * 10**-decimals + 1e-9


def _truncates_to(ours: float, printed: float, decimals: int) -> bool:
    scale = 10**decimals
    return abs(math.copysign(math.floor(abs(ours) * scale + 1e-9) / scale, ours) - printed) < 1e-9


def _check_table(name: str, cells: list[tuple[str, str, float, str]]):
    """cells: (row key, column, our full-precision value, printed text)."""
    misses, n_round, n_trunc, n_na = [], 0, 0, 0
    for row, col, ours, printed in cells:
        value, d = _parse(printed)
        if value is None:
            n_na += 1
            if not math.isnan(ours):
                misses.append(f"{name} {row} {col}: printed {printed!r}, ours {ours}")
            continue
        if (name, row, col) in TRUNCATED:
            if _truncates_to(ours, value, d) and not _rounds_to(ours, value, d):
                n_trunc += 1
            else:
                misses.append(f"{name} {row} {col}: listed as truncated, but ours {ours!r} "
                              f"vs printed {printed!r} is not a truncation-only match")
        elif _rounds_to(ours, value, d):
            n_round += 1
        else:
            misses.append(f"{name} {row} {col}: printed {printed!r}, ours {ours!r}")
    print(f"{name}: {n_round} cells round to print, {n_trunc} truncate to print, "
          f"{n_na} printed N/A or $-, {len(misses)} do not reproduce")
    assert n_round + n_trunc > 0, f"{name}: compared nothing"
    assert not misses, "\n".join(misses)


def _fixture(name):
    return pd.read_csv(ARTICLE / f"{name}.csv", dtype=str, keep_default_na=False)


def test_table1_every_cell(fitted):
    ours = report.annual_table(fitted)
    cols = {"trips_b_yr": "Trips (B/year)", "avg_bin_dist_mi": "Average Bin Distance (miles)",
            "calculated_vmt_b": "Calculated VMT (B/year)"}
    printed = _fixture("table1")
    assert list(printed["bin"]) == list(ours["Trip Distance Bin (miles)"])
    _check_table("table1", [(r["bin"], c, float(ours.iloc[i][v]), r[c])
                            for i, r in printed.iterrows() for c, v in cols.items()])


def test_table2_every_cell(fitted):
    modelled = fitted.vmt_miles_prenorm.sum(axis=1) / 1e9
    error = fitted.monthly_error_pct(prenorm=True)
    printed = _fixture("table2")
    cells = []
    for i, r in printed.iterrows():
        assert int(r["month"]) == fitted.months[i]
        cells += [(r["month"], "fhwa_vmt_b", float(fitted.fhwa_billion[i]), r["fhwa_vmt_b"]),
                  (r["month"], "model_vmt_b", float(modelled[i]), r["model_vmt_b"]),
                  (r["month"], "error_pct", float(error[i]), r["error_pct"])]
    _check_table("table2", cells)


def test_table3_every_cell(fitted, config):
    ours = report.table3(fitted, 50, config["paper_scenarios"]["households_millions"],
                         round_trip=config.round_trip)
    cols = {"avg_dist_mi": "Avg Dist (mi)", "trips_b_yr": "Trips (B/yr)",
            "trips_b_wk": "Trips (B/wk)", "trips_per_hh_wk": "Trips/HH/wk",
            "vmt_b_yr": "VMT (B/yr)", "ev_vmt_b_yr": "EV VMT (B/yr)",
            "gas_vmt_b_yr": "Gas VMT (B/yr)", "ev_pct_in_bin": "EV% in bin"}
    printed = _fixture("table3")
    assert list(printed["bin"]) == list(ours["Trip Distance Bin (miles)"])
    _check_table("table3", [(r["bin"], c, float(ours.iloc[i][v]), r[c])
                            for i, r in printed.iterrows() for c, v in cols.items()])


@pytest.fixture(scope="module")
def scen(fitted, config):
    return costs.scenario_table(fitted, config)


@pytest.fixture(scope="module")
def chg(fitted, config):
    return costs.charging_table(fitted, config, RAW)


TABLE5 = {c: c for c in ("Gas VMT (B)", "MPG", "Gallons (B)", "Gas Emissions (Mt CO2)",
                         "Electric VMT (B)", "Electricity (TWh)",
                         "Electricity Emissions (Mt CO2)", "Total Emissions (Mt CO2)",
                         "CO2 Saved (Mt CO2)")} | {"mi /kWh": "mi / kWh"}
# printed column -> (package column, multiplier to the printed unit)
TABLE6 = {"% EV VMT": ("% Electric", 100), "% Increase": ("% Increase", 100),
          "Battery Size Average (kWh)": ("Battery Size (kWh)", 1),
          "Battery Capacity (TWh)": ("Installed Battery (TWh)", 1),
          "Battery (Wh) /VMT": ("Battery Wh / VMT", 1),
          "Battery Cost $T": ("Battery Cost ($T)", 1),
          "$CAPEX /kg CO2": ("$ CAPEX / kg CO2", 1), "$CAPEX /EV Mile": ("$ CAPEX / EV Mile", 1),
          "$OPEX": ("OPEX ($B)", 1), "$OPEX /VMT": ("$ OPEX / VMT", 1),
          "$OPEX /kg CO2": ("$ OPEX / kg CO2", 1)}


def _scenario_cells(name, scen, columns):
    printed = _fixture(name)
    assert list(printed["Vehicle Type"]) == list(scen["Vehicle Type"])
    assert list(printed["Scenario"]) == list(scen["Scenario"])
    cells = []
    for i, r in printed.iterrows():
        key = f"{r['Scenario']}|{r['Vehicle Type']}"
        for col, spec in columns.items():
            src, mult = spec if isinstance(spec, tuple) else (spec, 1)
            value = float(scen.iloc[i][src])
            # The ICE row's battery cost is printed '$-': zero, shown as a dash.
            if r[col].strip() == "$-":
                assert value == 0.0, f"{key} {col}: printed $-, ours {value}"
                value = math.nan
            cells.append((key, col, value * mult, r[col]))
    return cells


def test_table5_every_cell(scen):
    _check_table("table5", _scenario_cells("table5", scen, TABLE5))


def test_table6_every_cell(scen):
    _check_table("table6", _scenario_cells("table6", scen, TABLE6))


# ===========================================================================
# Sentences in the prose that reproduce
# ===========================================================================

def _row(scen, scenario, vehicle):
    return scen[(scen["Scenario"] == scenario) & (scen["Vehicle Type"] == vehicle)].iloc[0]


def _avg(scen, r):
    return _row(scen, "Average", costs.ldv_label(r))


def _prose_values(fitted, config, scen):
    """(section, quoted text, our value in the quoted unit, printed number as text)."""
    base = {r: split_vmt(fitted, r, round_trip=config.round_trip) for r in (50, 100, 150)}
    old = metrics.summarize([base[50], base[150]], config).set_index("Range (mi)")
    ice = _row(scen, "Average", costs.ICE)
    ev = _row(scen, "Average", costs.EV)
    return [
        ("summary", "73.3% of VMT", base[50].ev_share_pct, "73.3"),
        ("summary", "2.391 T electric mi/yr", base[50].ev_billion / 1000, "2.391"),
        ("summary", "86.8% at 150 miles", base[150].ev_share_pct, "86.8"),
        ("summary", "(2.83 T)", base[150].ev_billion / 1000, "2.83"),
        ("summary", "574 Mt (50 mi)", _avg(scen, 50)["CO2 Saved (Mt CO2)"], "574"),
        ("summary", "0.072 USD/kg CO2 (50 mile)", _avg(scen, 50)["$ CAPEX / kg CO2"], "0.072"),
        ("4.3", "2.39 trillion electric miles", base[50].ev_billion / 1000, "2.39"),
        ("4.3", "573.9 Mt CO2 avoided", _avg(scen, 50)["CO2 Saved (Mt CO2)"], "573.9"),
        ("4.3", "Battery capacity per VMT 1.097 (50 mi)", _avg(scen, 50)["Battery Wh / VMT"],
         "1.097"),
        ("4.3", "to 3.291 (150 mi)", _avg(scen, 150)["Battery Wh / VMT"], "3.291"),
        ("4.3", "+320 B from 50 -> 100", base[100].ev_billion - base[50].ev_billion, "320"),
        ("4.3", "+121 B from 100 -> 150", base[150].ev_billion - base[100].ev_billion, "121"),
        ("4.3", "battery capacity from 3.6 [50 mi]", _avg(scen, 50)["Installed Battery (TWh)"],
         "3.6"),
        ("4.3", "to 10.7 TWh [150 mi]", _avg(scen, 150)["Installed Battery (TWh)"], "10.7"),
        # These four come from the OTHER model in this repository (metrics.summarize: a
        # 241.8 M-vehicle fleet, one year, 26.2 mpg, 387 g/kWh), not from the workbook
        # behind Table 6, which gives $0.017 and $0.044 per mile and $72 and $182 per
        # ton over ten years. Both are in the paper; see README.
        ("4.3", "USD 0.161/mi (50 mi)", old.loc[50.0, "$ / electric mile"], "0.161"),
        ("4.3", "to USD 0.409/mi (150 mi)", old.loc[150.0, "$ / electric mile"], "0.409"),
        ("4.3", "from USD 712/t", old.loc[50.0, "$ / ton CO2 saved"], "712"),
        ("4.3", "to USD 1802/t", old.loc[150.0, "$ / ton CO2 saved"], "1802"),
        ("conclusions", "rises from 73.3 %", base[50].ev_share_pct, "73.3"),
        ("conclusions", "to 86.8 %", base[150].ev_share_pct, "86.8"),
        ("conclusions", "increase from 574", _avg(scen, 50)["CO2 Saved (Mt CO2)"], "574"),
        ("conclusions", "to 680 Mt", _avg(scen, 150)["CO2 Saved (Mt CO2)"], "680"),
        ("conclusions", "0.072 USD/kg CO2 at 50 mi", _avg(scen, 50)["$ CAPEX / kg CO2"], "0.072"),
        ("conclusions", "to 0.182 USD/kg CO2 at 150 mi", _avg(scen, 150)["$ CAPEX / kg CO2"],
         "0.182"),
        ("conclusions", "11.4 cents/mi for ICEVs", ice["$ OPEX / VMT"] * 100, "11.4"),
        ("conclusions", "averages 4- [cents/mi]", ev["$ OPEX / VMT"] * 100, "4"),
        ("conclusions", "-8 cents/mi", _avg(scen, 50)["$ OPEX / VMT"] * 100, "8"),
        ("conclusions", "roughly 7- [TWh, 100 mi]", _avg(scen, 100)["Installed Battery (TWh)"],
         "7"),
        ("conclusions", "-9 TWh [125 mi]", _avg(scen, 125)["Installed Battery (TWh)"], "9"),
        ("conclusions", "USD 0.8- [trillion, 100 mi]", _avg(scen, 100)["Battery Cost ($T)"],
         "0.8"),
        ("conclusions", "-1.0 trillion [125 mi]", _avg(scen, 125)["Battery Cost ($T)"], "1.0"),
    ]


def test_prose_numbers_reproduce(fitted, config, scen):
    rows = _prose_values(fitted, config, scen)
    misses = []
    for where, quote, ours, printed in rows:
        value, d = _parse(printed)
        ok = _rounds_to(float(ours), value, d)
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
    printed = _fixture("table4").set_index("parameter")["printed_value"]
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


def test_up_to_75_percent_loss_is_not_in_the_workbook(chg):
    """Conclusions: charging fewer than five times a week "can lose up to 75% of
    potential electrified miles". The largest loss the workbook computes, two charges
    a week against seven, is 39%."""
    ev = chg.pivot(index="Vehicle Type", columns="Charges / week", values="Electric VMT (B)")
    worst_loss = float((1 - ev[[3, 2]].min(axis=1) / ev[7]).max())
    print(f"largest loss below five charges a week: {100 * worst_loss:.1f}%")
    assert 0.35 < worst_loss < 0.45
