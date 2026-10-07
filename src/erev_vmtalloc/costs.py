"""Tables 5-6 and the charging-frequency results: the Fall 2025 workbook's model.

The published Tables 4-6 and Figures 2-3 and 5-13 were computed in a spreadsheet,
``notebooks/fall-2025/Calculations Check_final.xlsx``, from this package's own VMT
split (its gas-VMT column holds this package's numbers, pasted). This module is that
spreadsheet's arithmetic, written once, in the order the sheet computes it. Each
column below names the workbook column it reproduces, so a disagreement can be traced
to one cell. ``tests/test_workbook_agreement.py`` compares every column with the
workbook's cached values, and ``tests/test_paper_numbers.py`` compares them with the
article's printed tables.

Two sheets, two tables:

- ``scenario_table``: 'Calcs by Scenario' rows 25-48. Worst, Average and Best, each
  for an ICE fleet, an EREV fleet at each range, and an all-electric fleet. Tables 5-6,
  Figures 2-3, 6, 8, 10 and 12.
- ``charging_table``: 'Calcs by Charge' rows 2-25. The Average scenario at 7, 5, 3
  and 2 charges per week. Figures 5, 7, 9, 11 and 13.

Units: VMT in billions of miles, energy in TWh, emissions in Mt CO2, money in $B
unless a column says $T or $ per unit.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .allocation import FittedVmt, ev_ratio_per_bin, split_vmt

ICE = "ICE"
EV = "EV"


def ldv_label(electric_range: float) -> str:
    """The workbook's and the article's name for an EREV fleet at one range."""
    return f"LDV ({int(electric_range)}-mile EV range)"


def _rows(
    *,
    scenario: str,
    params: dict,
    total_vmt_b: float,
    gas_vmt_b: list[float],
    battery_range_mi: list[float],
    elec_price: list[float],
    vehicles: float,
    lifespan_years: float,
    kg_co2_per_gal: float,
) -> pd.DataFrame:
    """The sheet's per-row arithmetic (columns D..AG) for one block of rows."""
    D = np.full(len(gas_vmt_b), float(total_vmt_b))
    E = np.asarray(gas_vmt_b, float)
    F = float(params["mpg"])
    G = E / F                                         # gallons, B
    H = float(kg_co2_per_gal)
    I = G * H                                         # gas emissions, Mt   # noqa: E741
    J = D - E                                         # electric VMT, B
    K = J / D                                         # share electric
    M = float(params["mi_per_kwh"])
    N = J / M                                         # electricity, TWh
    O = float(params["grid_g_per_kwh"])  # noqa: E741
    P = N * O * 1000 / 1e6                            # electricity emissions, Mt
    Q = P + I                                         # total emissions, Mt
    S = np.asarray(battery_range_mi, float) / M       # battery size, kWh
    T = S * vehicles / 1e6 / 1000                     # installed battery, TWh
    U = T / D * 1000                                  # battery Wh per mile of VMT
    V = float(params["pack_usd_per_kwh"])
    W = T * V / 1000                                  # installed battery cost, $T
    Z = float(params["gas_usd_per_gal"])
    AA = Z * G                                        # gas operating cost, $B
    AB = np.asarray(elec_price, float)
    AC = AB * N                                       # electricity operating cost, $B
    AD = AC + AA                                      # operating cost, $B
    AF = AD / D                                       # operating cost per VMT, $
    with np.errstate(divide="ignore", invalid="ignore"):
        Y = np.where(J > 0, W / (J * lifespan_years) * 1000, np.nan)

    return pd.DataFrame(
        {
            "Scenario": scenario,
            "VMT (B)": D,
            "Gas VMT (B)": E,
            "MPG": F,
            "Gallons (B)": G,
            "kg CO2 / gallon": H,
            "Gas Emissions (Mt CO2)": I,
            "Electric VMT (B)": J,
            "% Electric": K,
            "mi / kWh": M,
            "Electricity (TWh)": N,
            "Grid g CO2 / kWh": O,
            "Electricity Emissions (Mt CO2)": P,
            "Total Emissions (Mt CO2)": Q,
            "Battery Size (kWh)": S,
            "Installed Battery (TWh)": T,
            "Battery Wh / VMT": U,
            "Pack $ / kWh": V,
            "Battery Cost ($T)": W,
            "$ CAPEX / EV Mile": Y,
            "$ / gallon": Z,
            "Gas OPEX ($B)": AA,
            "$ / kWh": AB,
            "Electricity OPEX ($B)": AC,
            "OPEX ($B)": AD,
            "$ OPEX / VMT": AF,
        }
    )


def _savings(frame: pd.DataFrame, ice_total_mt: float, ice_opex_b: float, lifespan_years: float):
    """Columns R, X, AE, AG: everything measured against an ICE baseline."""
    R = ice_total_mt - frame["Total Emissions (Mt CO2)"]
    frame["CO2 Saved (Mt CO2)"] = R
    with np.errstate(divide="ignore", invalid="ignore"):
        frame["$ CAPEX / kg CO2"] = np.where(
            R != 0, frame["Battery Cost ($T)"] / (R * lifespan_years) * 1000, np.nan
        )
        frame["$ OPEX / kg CO2"] = np.where(R != 0, frame["OPEX ($B)"] / R, np.nan)
    frame["OPEX Savings ($B)"] = ice_opex_b - frame["OPEX ($B)"]
    return frame


def scenario_table(fitted: FittedVmt, config) -> pd.DataFrame:
    """'Calcs by Scenario' rows 25-48: Tables 5 and 6.

    One block per scenario, in workbook order: ICE, LDV at each range, EV. Gas VMT for
    the LDV rows comes from this package's base-case split on FHWA-normalised VMT,
    which is what the workbook pasted in.
    """
    paper = config["paper_scenarios"]
    total = fitted.annual_vmt_billion
    ranges = [float(r) for r in paper["ranges"]]
    gas = [total] + [
        split_vmt(fitted, r, round_trip=config.round_trip).gas_billion for r in ranges
    ] + [0.0]
    battery = [0.0] + ranges + [float(paper["ev_row_range_mi"])]
    labels = [ICE] + [ldv_label(r) for r in ranges] + [EV]

    blocks = []
    for name, params in paper["scenarios"].items():
        price = float(params["elec_usd_per_kwh"])
        prices = [price] * (len(labels) - 1) + [
            float(params.get("elec_usd_per_kwh_ev_row", price))
        ]
        block = _rows(
            scenario=name,
            params=params,
            total_vmt_b=total,
            gas_vmt_b=gas,
            battery_range_mi=battery,
            elec_price=prices,
            vehicles=float(paper["vehicles"]),
            lifespan_years=float(paper["lifespan_years"]),
            kg_co2_per_gal=float(paper["kg_co2_per_gal"]),
        )
        block.insert(1, "Vehicle Type", labels)
        block.insert(10, "% Increase", block["% Electric"].diff())
        block.loc[0, "% Increase"] = np.nan
        _savings(
            block,
            ice_total_mt=float(block.loc[0, "Total Emissions (Mt CO2)"]),
            ice_opex_b=float(block.loc[0, "OPEX ($B)"]),
            lifespan_years=float(paper["lifespan_years"]),
        )
        # The ICE row has no capital cost and no saving to divide by.
        block.loc[0, ["$ CAPEX / kg CO2", "$ CAPEX / EV Mile", "$ OPEX / kg CO2"]] = np.nan
        blocks.append(block)
    return pd.concat(blocks, ignore_index=True)


def load_charging_gas_vmt(raw_dir: Path, filename: str) -> pd.DataFrame:
    """The 5-, 3- and 2-day gas VMT: pasted constants with no surviving generator."""
    path = Path(raw_dir) / filename
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; it is a committed input, see its .meta.yaml")
    # round_trip: the default C parser can be off in the last digit, and these values
    # are compared with the workbook's exactly.
    frame = pd.read_csv(path, float_precision="round_trip")
    expected = {"charges_per_week", "electric_range_mi", "gas_vmt_billion"}
    if set(frame.columns) != expected:
        raise ValueError(f"{path}: columns {sorted(frame.columns)}, expected {sorted(expected)}")
    return frame


def table1_printed_total_b(fitted: FittedVmt) -> float:
    """The sum of Table 1's printed VMT column: 3,392.497 B.

    Printed trips times printed average distance, summed. It is the fit BEFORE
    normalisation to FHWA (3,385.0 B, 3.74% above FHWA's 3,262.8 B), plus the 0-1 mile
    bin's display rounding of 0.25 to 0.3 miles (a further 7.5 B). The published
    charging-frequency figures stand on this number.
    """
    from .report import annual_table

    return float(annual_table(fitted)["Calculated VMT (B/year)"].sum())


def charging_total_vmt_b(fitted: FittedVmt, config) -> float:
    """The annual VMT the charging results stand on; see config `vmt_basis`."""
    basis = config["paper_scenarios"]["charging"]["vmt_basis"]
    if basis == "table1_printed":
        return table1_printed_total_b(fitted)
    if basis == "normalized":
        return fitted.annual_vmt_billion
    raise ValueError(f"paper_scenarios.charging.vmt_basis must be 'table1_printed' or "
                     f"'normalized', got {basis!r}")


def short_trip_electric_vmt_b(fitted: FittedVmt, electric_range: float, config) -> float:
    """Electric VMT at one range from trips under 100 miles, FHWA-normalised, billions.

    The bins in `paper_scenarios.charging.long_trip_bins` are excluded: Section 4.6
    has drivers charge before a long trip, so charging frequency does not touch it.
    """
    long_bins = set(config["paper_scenarios"]["charging"]["long_trip_bins"])
    unknown = long_bins - set(fitted.bins)
    if unknown:
        raise ValueError(f"long_trip_bins names bins the fit does not have: {sorted(unknown)}")
    short = np.array([b not in long_bins for b in fitted.bins])
    ratio = ev_ratio_per_bin(electric_range, fitted.mean_distance, round_trip=config.round_trip)
    return float((fitted.annual_vmt_billion_per_bin * ratio)[short].sum())


def charging_table(fitted: FittedVmt, config, raw_dir: Path) -> pd.DataFrame:
    """'Calcs by Charge' rows 2-25: the charging-frequency figures.

    Seven charges a week is the base-case split's gas share applied to the chosen VMT
    total. Five, three and two add a fixed share of short-trip electric VMT to that,
    as gas (config `missed_charge_loss`): the rule recovered for the workbook's typed
    constants, which it reproduces to within 3.4e-6. `gas_source: pasted` reads those
    constants instead. Both stand on the chosen VMT total.

    CO2 and operating-cost savings are measured against the Average scenario's ICE
    row in `scenario_table`, exactly as the workbook does. Under the default basis
    that baseline stands on 3,262.8 B miles while these rows stand on 3,392.5 B, so
    the published savings are understated; the README states by how much.
    """
    paper = config["paper_scenarios"]
    charging = paper["charging"]
    params = paper["scenarios"][charging["scenario"]]
    total = charging_total_vmt_b(fitted, config)
    pasted_basis = table1_printed_total_b(fitted)
    source = charging.get("gas_source", "regenerated")
    if source not in ("regenerated", "pasted"):
        raise ValueError(f"paper_scenarios.charging.gas_source must be 'regenerated' or "
                         f"'pasted', got {source!r}")
    pasted = (load_charging_gas_vmt(raw_dir, charging["gas_vmt_file"])
              if source == "pasted" else None)
    loss = {int(k): float(v) for k, v in charging["missed_charge_loss"].items()}
    scale = total / fitted.annual_vmt_billion
    ranges = [float(r) for r in paper["ranges"]]

    rows = []
    for cpw in charging["frequencies"]:
        for r in ranges:
            split = split_vmt(fitted, r, round_trip=config.round_trip)
            seven = total * split.gas_billion / (split.ev_billion + split.gas_billion)
            if int(cpw) == 7:
                gas = seven
            elif source == "regenerated":
                if int(cpw) not in loss:
                    raise ValueError(f"missed_charge_loss has no share for {cpw} charges/week")
                short = short_trip_electric_vmt_b(fitted, r, config) * scale
                gas = seven + loss[int(cpw)] * short
            else:
                match = pasted[
                    (pasted["charges_per_week"] == int(cpw))
                    & (pasted["electric_range_mi"] == int(r))
                ]
                if len(match) != 1:
                    raise ValueError(f"{charging['gas_vmt_file']}: no single row for "
                                     f"{cpw} charges/week at {r:g} mi")
                gas = float(match["gas_vmt_billion"].iloc[0]) * total / pasted_basis
            rows.append((int(cpw), r, gas))

    frame = _rows(
        scenario=charging["scenario"],
        params=params,
        total_vmt_b=total,
        gas_vmt_b=[g for _, _, g in rows],
        battery_range_mi=[r for _, r, _ in rows],
        elec_price=[float(params["elec_usd_per_kwh"])] * len(rows),
        vehicles=float(paper["vehicles"]),
        lifespan_years=float(paper["lifespan_years"]),
        kg_co2_per_gal=float(paper["kg_co2_per_gal"]),
    )
    frame.insert(1, "Charges / week", [c for c, _, _ in rows])
    frame.insert(2, "Vehicle Type", [ldv_label(r) for _, r, _ in rows])

    scen = scenario_table(fitted, config)
    ice = scen[(scen["Scenario"] == charging["scenario"]) & (scen["Vehicle Type"] == ICE)].iloc[0]
    _savings(
        frame,
        ice_total_mt=float(ice["Total Emissions (Mt CO2)"]),
        ice_opex_b=float(ice["OPEX ($B)"]),
        lifespan_years=float(paper["lifespan_years"]),
    )
    # The workbook's 'EV VMT Difference' block: how far each row's electric VMT sits
    # from the same range in the scenario table. Nonzero at 7 charges a week only
    # because the two tables stand on different VMT totals.
    scen_ev = scen[scen["Scenario"] == charging["scenario"]].set_index("Vehicle Type")[
        "Electric VMT (B)"
    ]
    frame["Scenario Electric VMT (B)"] = frame["Vehicle Type"].map(scen_ev)
    return frame


def figure_data(scen: pd.DataFrame, chg: pd.DataFrame, config) -> pd.DataFrame:
    """Every series in published Figures 2-3 and 5-13, long format, in its plotted units.

    One row per plotted value: figure, series, x (range in miles, or ICE / EV), and y.
    The units are the figure's own axis units (trillions, Bt, $ per ton), so this
    table can be compared with what the frozen notebook actually drew.
    """
    out = []

    def add(fig, series, xs, ys):
        out.extend({"figure": fig, "series": series, "x": str(x), "y": float(y)}
                   for x, y in zip(xs, ys, strict=True))

    ldv = scen[scen["Vehicle Type"].str.startswith("LDV")]
    for name in config["paper_scenarios"]["scenarios"]:
        s = ldv[ldv["Scenario"] == name]
        xs = [int(v.split("(")[1].split("-")[0]) for v in s["Vehicle Type"]]
        add(2, f"{name} installed battery (TWh)", xs, s["Installed Battery (TWh)"])
        add(3, f"{name} battery capital cost ($T)", xs, s["Battery Cost ($T)"])
        add(8, f"{name} CAPEX per EV mile ($)", xs, s["$ CAPEX / EV Mile"])
        add(8, f"{name} electric VMT (T)", xs, s["Electric VMT (B)"] / 1000)
        add(10, f"{name} CAPEX per ton CO2 saved ($)", xs, s["$ CAPEX / kg CO2"] * 1000)
        add(10, f"{name} CO2 saved (Mt)", xs, s["CO2 Saved (Mt CO2)"])
        add(12, f"{name} gas OPEX ($B)", xs, s["Gas OPEX ($B)"])
        add(12, f"{name} electricity OPEX ($B)", xs, s["Electricity OPEX ($B)"])
        full = scen[scen["Scenario"] == name]
        xs6 = ["ICE"] + xs + ["EV"]
        add(6, f"{name} gas CO2 (Bt)", xs6, full["Gas Emissions (Mt CO2)"] / 1000)
        add(6, f"{name} grid CO2 (Bt)", xs6, full["Electricity Emissions (Mt CO2)"] / 1000)

    paper = config["paper_scenarios"]
    params = paper["scenarios"][paper["charging"]["scenario"]]
    total = float(chg["VMT (B)"].iloc[0])
    kg = float(config["paper_scenarios"]["kg_co2_per_gal"])
    for cpw, c in chg.groupby("Charges / week", sort=False):
        xs = [int(v.split("(")[1].split("-")[0]) for v in c["Vehicle Type"]]
        add(5, f"{cpw}/week electric VMT (T)", xs, c["Electric VMT (B)"] / 1000)
        add(5, f"{cpw}/week gas VMT (T)", xs, c["Gas VMT (B)"] / 1000)
        add(7, f"{cpw}/week gas CO2 (Bt)", xs, c["Gas Emissions (Mt CO2)"] / 1000)
        add(7, f"{cpw}/week grid CO2 (Bt)", xs, c["Electricity Emissions (Mt CO2)"] / 1000)
        add(9, f"{cpw}/week CAPEX per EV mile ($)", xs, c["$ CAPEX / EV Mile"])
        add(9, f"{cpw}/week electric VMT (T)", xs, c["Electric VMT (B)"] / 1000)
        add(11, f"{cpw}/week CAPEX per ton CO2 saved ($)", xs, c["$ CAPEX / kg CO2"] * 1000)
        add(11, f"{cpw}/week CO2 saved (Mt)", xs, c["CO2 Saved (Mt CO2)"])
        add(13, f"{cpw}/week gas OPEX ($B)", xs, c["Gas OPEX ($B)"])
        add(13, f"{cpw}/week electricity OPEX ($B)", xs, c["Electricity OPEX ($B)"])
    # Figure 5's dots: electric VMT "if charged before each trip", which the notebook
    # takes from the 7-a-week bars. Figure 7's ICE and EV bars: computed in the
    # notebook cell on the charging table's VMT total, not taken from Figure 6.
    seven = chg[chg["Charges / week"] == 7]
    add(5, "dots: electric VMT if charged before each trip (T)",
        [int(v.split("(")[1].split("-")[0]) for v in seven["Vehicle Type"]],
        seven["Electric VMT (B)"] / 1000)
    add(7, "ICE gas CO2 (Bt)", ["ICE"], [total / float(params["mpg"]) * kg / 1000])
    add(7, "EV grid CO2 (Bt)", ["EV"],
        [total / float(params["mi_per_kwh"]) * float(params["grid_g_per_kwh"]) / 1e6])

    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Figure 4: one household's week
# ---------------------------------------------------------------------------

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def weekly_trips_per_household(fitted: FittedVmt, config) -> np.ndarray:
    """Trips per household per week, by bin: the workbook's 'Trip Bin Distance'!I column.

    Derived as the workbook did, rounding included (config `weekly_profile`): Table 1's
    December trips as printed, per driver per month, then per week.
    """
    from .report import month_table

    wp = config["paper_scenarios"]["weekly_profile"]
    month = month_table(fitted, int(wp["month"]))["Trips (B/month)"].to_numpy(float)
    per_driver_month = np.round(month * 1000 / float(wp["drivers_millions"]), 4)
    return np.round(per_driver_month * 12 / float(wp["weeks_per_year"]), 4)


def weekly_profile(fitted: FittedVmt, config) -> np.ndarray:
    """Miles driven each day, Monday to Sunday, by the household Figure 4 follows."""
    wp = config["paper_scenarios"]["weekly_profile"]
    trips = weekly_trips_per_household(fitted, config)
    weekly_miles = float((trips * fitted.mean_distance).sum())
    weights = np.asarray(wp["day_weights"], float)
    if weights.shape != (7,):
        raise ValueError("weekly_profile.day_weights needs seven values, Monday to Sunday")
    return weights / weights.sum() * weekly_miles


def simulate_week(electric_range: float, daily_miles, charge_nights) -> pd.DataFrame:
    """One week under the published notebook's rule: drive on battery while it lasts,
    then on gas; recharge to full at the end of each charge night. Monday starts full."""
    nights = {int(n) for n in charge_nights}
    soc = float(electric_range)
    rows = []
    for i, need in enumerate(np.asarray(daily_miles, float)):
        start = soc
        ev = min(soc, need)
        soc = max(0.0, soc - ev)
        if i in nights:
            soc = float(electric_range)
        rows.append({"day": DAYS[i], "miles": need, "ev_miles": ev, "gas_miles": need - ev,
                     "soc_start": start})
    return pd.DataFrame(rows)


def figure4_data(fitted: FittedVmt, config) -> pd.DataFrame:
    """Every panel of Figure 4 (charges per week x range): each day's EV and gas miles
    and start-of-day battery range, in the long format `figure_data` uses."""
    wp = config["paper_scenarios"]["weekly_profile"]
    daily = weekly_profile(fitted, config)
    out = []
    for cpw, nights in wp["charge_nights"].items():
        for r in wp["ranges"]:
            week = simulate_week(float(r), daily, nights)
            for col, name in (("ev_miles", "EV miles"), ("gas_miles", "gas miles"),
                              ("soc_start", "start-of-day range")):
                for day, v in zip(week["day"], week[col], strict=True):
                    out.append({"figure": 4, "series": f"{int(cpw)}/week R={int(r)} {name}",
                                "x": day, "y": float(v)})
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Figure 1: emissions and VMT by transport subsector, 2022
# ---------------------------------------------------------------------------

FIGURE1_ORDER = ["LDV", "EREV 100 mi (nat. avgs.)", "Combination Truck",
                 "Non Transport Vehicles", "SU Truck", "Aircraft", "Pipeline", "Watercraft",
                 "Rail", "Buses"]


def figure1_data(scen: pd.DataFrame, fitted: FittedVmt, raw_dir: Path) -> pd.DataFrame:
    """Figure 1's bars (CO2, billion t) and dots (VMT, trillion miles), in plotted order.

    Road modes' CO2 is vehicles x miles / mpg x kg per gallon, as the Copy workbook's
    'Rough1' sheet computes it; other modes' CO2 is typed there. The EREV bar is the
    Average scenario's 100-mile total emissions (Table 5). The dots are the VMT values
    typed in the figure's cell, five of them placeholders (see the input's sidecar),
    except LDV and EREV, which the cell sets to the total VMT.
    """
    rows = pd.read_csv(Path(raw_dir) / "transport_subsectors_2022.csv").set_index("figure_label")
    road = rows["vehicles"].notna()
    co2_mt = rows["emissions_mt"].copy()
    co2_mt[road] = (rows.loc[road, "vehicles"] * rows.loc[road, "miles_per_vehicle"] / 1e9
                    / rows.loc[road, "mpg"] * rows.loc[road, "kg_co2_per_gal"])
    vmt_t = rows["fhwa_vmt_million"] / 1e6
    erev = scen[(scen["Scenario"] == "Average")
                & (scen["Vehicle Type"] == ldv_label(100))]["Total Emissions (Mt CO2)"]
    co2_mt["EREV 100 mi (nat. avgs.)"] = float(erev.iloc[0])
    vmt_t["LDV"] = vmt_t["EREV 100 mi (nat. avgs.)"] = fitted.annual_vmt_billion / 1000
    out = []
    for label in FIGURE1_ORDER:
        out.append({"figure": 1, "series": "CO2 (Bt)", "x": label, "y": co2_mt[label] / 1000})
        out.append({"figure": 1, "series": "VMT (T)", "x": label, "y": float(vmt_t[label])})
    return pd.DataFrame(out)
