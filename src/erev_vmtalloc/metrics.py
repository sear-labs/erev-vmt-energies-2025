"""Emissions, battery sizing and cost derived from an allocation.

Everything here is a per-mile or per-vehicle factor applied to the split; no
fitting happens. Units are stated on every function because the mixture of
grams, tons, kWh, TWh and billions is where this class of calculation goes
wrong without ever looking wrong.
"""

from __future__ import annotations

import pandas as pd

from .allocation import Split


def gasoline_g_per_mile(mpg_gas: float, co2_per_gal: float) -> float:
    """g CO2 per gasoline mile."""
    return co2_per_gal / mpg_gas


def electric_g_per_mile(ev_kwh_per_mi: float, grid_g_per_kwh: float) -> float:
    """g CO2 per electric mile, at national average grid intensity."""
    return ev_kwh_per_mi * grid_g_per_kwh


def fleet_size(total_vmt_billion: float, avg_driver_miles: float) -> float:
    """Number of vehicles implied by total VMT and average annual miles."""
    return (total_vmt_billion * 1e9) / avg_driver_miles


def pack_kwh(electric_range: float, eta_mi_per_kwh: float) -> float:
    """Usable pack size in kWh needed for one electric range, in miles."""
    return electric_range / eta_mi_per_kwh


def summarize(splits: list[Split], config) -> pd.DataFrame:
    """One row per electric range: shares, emissions saved, battery and cost.

    Args:
        splits: allocations, one per electric range, all from the same scenario.
        config: a loaded Config.
    """
    emissions = config["emissions"]
    battery = config["battery"]

    gas_g_per_mi = gasoline_g_per_mile(emissions["mpg_gas"], emissions["co2_per_gal"])
    ev_g_per_mi = electric_g_per_mile(
        emissions["ev_kwh_per_mi"], emissions["grid_g_per_kwh"]
    )
    delta_g_per_mi = gas_g_per_mi - ev_g_per_mi

    rows = []
    for split in splits:
        total_billion = split.ev_billion + split.gas_billion
        n_vehicles = fleet_size(total_billion, config["fleet"]["avg_driver_miles"])

        ev_miles = split.ev_billion * 1e9
        size_kwh = pack_kwh(split.electric_range, battery["eta_mi_per_kwh"])
        installed_kwh = n_vehicles * size_kwh
        # Grams to metric tons is 1e6, applied once: g/mi * mi -> g -> t.
        co2_saved_tons = (ev_miles * delta_g_per_mi) / 1e6
        fleet_cost = installed_kwh * battery["pack_cost_per_kwh"]

        rows.append(
            {
                "Range (mi)": split.electric_range,
                "Scenario": split.scenario,
                "EV share (%)": split.ev_share_pct,
                "EV VMT (B)": split.ev_billion,
                "Gas VMT (B)": split.gas_billion,
                "EV CO2 saved (Mt)": co2_saved_tons / 1e6,
                "Battery size (kWh)": size_kwh,
                "Installed battery (TWh)": installed_kwh / 1e9,
                "kWh battery / electric mile": installed_kwh / max(ev_miles, 1.0),
                "kWh battery / ton CO2 saved": installed_kwh / max(co2_saved_tons, 1e-9),
                "Fleet pack cost ($B)": fleet_cost / 1e9,
                "$ / electric mile": fleet_cost / max(ev_miles, 1.0),
                "$ / ton CO2 saved": fleet_cost / max(co2_saved_tons, 1e-9),
            }
        )

    return pd.DataFrame(rows).sort_values("Range (mi)").reset_index(drop=True)
