"""The package against the frozen Fall 2025 workbook, cell by cell.

src/erev_vmtalloc/costs.py re-implements the spreadsheet that produced Tables 4-6 and
Figures 2-3, 5-13. This compares every column it computes with the value the workbook
cached for that cell when it was last saved. Agreement here means the package does the
same arithmetic on the same inputs. Whether those inputs and that arithmetic are what
the article PRINTS is a separate question, answered in tests/test_paper_numbers.py.

Tolerance: 1e-6 relative. The workbook's gas-VMT inputs are this package's numbers
pasted at six decimals (871.73127 for 871.7312697...), a difference near 1e-9; anything
a formula got wrong is orders of magnitude larger. The charging sheet's VMT total,
3392.497, is reproduced exactly: it is the sum of Table 1's printed VMT column.

The charging sheet gets 2e-5. Its 7-a-week gas VMT is pasted, and the package derives
it (base-case gas share times 3392.497). The two differ by 1e-6 to 8e-6 relative,
growing with range (at most 0.0036 B miles): the paste came from some rounded
intermediate that does not survive. That is noise far below anything printed, and a
formula error moves a cell by 1e-3 or more, so 2e-5 sits between the two.

The workbook is read with openpyxl, a dev dependency. Nothing in the package or the
verification notebook needs it.
"""
from __future__ import annotations

import math
from pathlib import Path

# A plain import, not pytest.importorskip: a skip would report green on any machine
# without the dev extras, which is this guard failing silently.
import openpyxl
import pytest

from erev_vmtalloc import costs, report

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "notebooks" / "fall-2025" / "Calculations Check_final.xlsx"
RAW = ROOT / "data" / "raw"
REL_TOL = 1e-6
CHARGING_REL_TOL = 2e-5

# package column -> workbook column, 'Calcs by Scenario' rows 25-48
SCENARIO_COLUMNS = {
    "VMT (B)": "D", "Gas VMT (B)": "E", "MPG": "F", "Gallons (B)": "G",
    "kg CO2 / gallon": "H", "Gas Emissions (Mt CO2)": "I", "Electric VMT (B)": "J",
    "% Electric": "K", "% Increase": "L", "mi / kWh": "M", "Electricity (TWh)": "N",
    "Grid g CO2 / kWh": "O", "Electricity Emissions (Mt CO2)": "P",
    "Total Emissions (Mt CO2)": "Q", "CO2 Saved (Mt CO2)": "R", "Battery Size (kWh)": "S",
    "Installed Battery (TWh)": "T", "Battery Wh / VMT": "U", "Pack $ / kWh": "V",
    "Battery Cost ($T)": "W", "$ CAPEX / kg CO2": "X", "$ CAPEX / EV Mile": "Y",
    "$ / gallon": "Z", "Gas OPEX ($B)": "AA", "$ / kWh": "AB", "Electricity OPEX ($B)": "AC",
    "OPEX ($B)": "AD", "OPEX Savings ($B)": "AE", "$ OPEX / VMT": "AF",
    "$ OPEX / kg CO2": "AG",
}
# package column -> workbook column, 'Calcs by Charge' rows 2-25 (one column to the left)
CHARGING_COLUMNS = {
    "VMT (B)": "C", "Gas VMT (B)": "D", "MPG": "E", "Gallons (B)": "F",
    "kg CO2 / gallon": "G", "Gas Emissions (Mt CO2)": "H", "Electric VMT (B)": "I",
    "% Electric": "J", "mi / kWh": "L", "Electricity (TWh)": "M", "Grid g CO2 / kWh": "N",
    "Electricity Emissions (Mt CO2)": "O", "Total Emissions (Mt CO2)": "P",
    "CO2 Saved (Mt CO2)": "Q", "Battery Size (kWh)": "R", "Installed Battery (TWh)": "S",
    "Battery Wh / VMT": "T", "Pack $ / kWh": "U", "Battery Cost ($T)": "V",
    "$ CAPEX / kg CO2": "W", "$ CAPEX / EV Mile": "X", "$ / gallon": "Y",
    "Gas OPEX ($B)": "Z", "$ / kWh": "AA", "Electricity OPEX ($B)": "AB", "OPEX ($B)": "AC",
    "OPEX Savings ($B)": "AD", "$ OPEX / VMT": "AE", "$ OPEX / kg CO2": "AF",
}


@pytest.fixture(scope="module")
def workbook():
    return openpyxl.load_workbook(WORKBOOK, data_only=True)


@pytest.fixture(scope="module")
def scen(fitted, config):
    return costs.scenario_table(fitted, config)


@pytest.fixture(scope="module")
def chg(fitted, config):
    return costs.charging_table(fitted, config, RAW)


def _cached(sheet, cell):
    """The cached number, NaN for an empty cell, None for typed text (no formula)."""
    value = sheet[cell].value
    if value is None:
        return math.nan
    if isinstance(value, str):
        return None
    return float(value)


def _compare(frame, sheet, columns, first_row, label, tol=REL_TOL):
    """Every cell; print the worst relative gap per column; fail listing every miss."""
    misses, checked, typed = [], 0, []
    for name, col in columns.items():
        worst = 0.0
        for i, ours in enumerate(frame[name]):
            theirs = _cached(sheet, f"{col}{first_row + i}")
            if theirs is None:
                # Typed text such as 'N/A' where the column otherwise has a formula:
                # the workbook computed nothing there, so there is nothing to compare.
                typed.append(f"{col}{first_row + i}")
                continue
            if math.isnan(theirs) or (isinstance(ours, float) and math.isnan(ours)):
                if not (math.isnan(theirs) and math.isnan(float(ours))):
                    # The workbook leaves some derived cells blank; only a value we
                    # compute where it has one, or the reverse with a nonzero, counts.
                    if not (math.isnan(theirs) and float(ours) == 0.0):
                        misses.append(f"{label} {col}{first_row + i} {name}: ours {ours}, "
                                      f"workbook {theirs}")
                continue
            checked += 1
            gap = abs(float(ours) - theirs) / max(abs(theirs), 1e-12)
            worst = max(worst, gap)
            if gap > tol:
                misses.append(f"{label} {col}{first_row + i} {name}: ours {float(ours)!r}, "
                              f"workbook {theirs!r}, rel {gap:.2e}")
        print(f"{label:>8} {col:>2} {name:<32} worst rel gap {worst:.1e}")
    print(f"{label}: {checked} cells compared, {len(misses)} outside {tol:g}; "
          f"typed text skipped at {typed}")
    assert checked > 500, f"only {checked} cells compared - the read found nothing"
    assert not misses, "\n".join(misses)


def test_scenario_sheet_matches(scen, workbook):
    assert len(scen) == 24
    sheet = workbook["Calcs by Scenario"]
    assert list(scen["Vehicle Type"]) == [sheet[f"C{r}"].value for r in range(25, 49)]
    assert list(scen["Scenario"]) == [sheet[f"B{r}"].value for r in range(25, 49)]
    _compare(scen, sheet, SCENARIO_COLUMNS, 25, "scenario")


def test_charging_sheet_matches(chg, workbook):
    assert len(chg) == 24
    sheet = workbook["Calcs by Charge"]
    assert list(chg["Charges / week"]) == [sheet[f"A{r}"].value for r in range(2, 26)]
    assert list(chg["Vehicle Type"]) == [sheet[f"B{r}"].value for r in range(2, 26)]
    _compare(chg, sheet, CHARGING_COLUMNS, 2, "charging", tol=CHARGING_REL_TOL)


def test_seven_a_week_is_the_base_share_of_the_unnormalised_total(chg):
    """The workbook pastes the 7-day gas VMT; the package derives it. They must agree.

    This is the origin of the 4% gap: the same gas share as Table 5, applied to
    3,392.5 B miles instead of 3,262.8 B.
    """
    pasted = costs.load_charging_gas_vmt(RAW, "charging_gas_vmt_2023.csv")
    pasted = pasted[pasted["charges_per_week"] == 7]["gas_vmt_billion"].to_numpy()
    ours = chg[chg["Charges / week"] == 7]["Gas VMT (B)"].to_numpy()
    gaps = abs(ours - pasted) / pasted
    print("7/week gas VMT, derived vs pasted, rel gaps:", [f"{g:.1e}" for g in gaps])
    assert (gaps < CHARGING_REL_TOL).all()


def test_raw_charging_extract_is_the_workbook(workbook):
    """data/raw/charging_gas_vmt_2023.csv holds exactly 'Calcs by Charge'!D2:D25."""
    sheet = openpyxl.load_workbook(WORKBOOK)["Calcs by Charge"]
    extract = costs.load_charging_gas_vmt(RAW, "charging_gas_vmt_2023.csv")
    for i, row in extract.iterrows():
        cell = sheet[f"D{i + 2}"].value
        assert not (isinstance(cell, str) and cell.startswith("=")), "D column became a formula"
        assert row["gas_vmt_billion"] == cell, (i + 2, row["gas_vmt_billion"], cell)
        assert row["charges_per_week"] == sheet[f"A{i + 2}"].value


def test_weekly_trips_per_household_is_the_workbook_column(fitted, config, workbook):
    """Figure 4's input, derived (December trips / 128 M drivers, x 12 / 52.14 weeks),
    equals the workbook's typed 'Trip Bin Distance'!I2:I11 exactly, and the per-driver
    step equals its typed F2:F11 exactly."""
    sheet = workbook["Trip Bin Distance"]
    ours = costs.weekly_trips_per_household(fitted, config)
    assert list(ours) == [sheet[f"I{r}"].value for r in range(2, 12)]
    # The per-driver step, forward: December's printed trips x 1000 / 128 M drivers.
    wp = config["paper_scenarios"]["weekly_profile"]
    december = report.month_table(fitted, int(wp["month"]))["Trips (B/month)"]
    per_driver = [round(v * 1000 / float(wp["drivers_millions"]), 4) for v in december]
    assert per_driver == [sheet[f"F{r}"].value for r in range(2, 12)]


def test_regenerated_charging_gas_equals_the_pasted_constants(chg):
    """The recovered rule reproduces all 18 typed 5-, 3- and 2-day gas VMT values."""
    pasted = costs.load_charging_gas_vmt(RAW, "charging_gas_vmt_2023.csv")
    worst = 0.0
    for row in pasted[pasted.charges_per_week != 7].itertuples():
        ours = chg[(chg["Charges / week"] == row.charges_per_week)
                   & (chg["Vehicle Type"] == costs.ldv_label(row.electric_range_mi))]
        gap = abs(float(ours["Gas VMT (B)"].iloc[0]) - row.gas_vmt_billion) / row.gas_vmt_billion
        worst = max(worst, gap)
    print(f"18 regenerated values, worst rel gap {worst:.1e}")
    assert worst < CHARGING_REL_TOL
