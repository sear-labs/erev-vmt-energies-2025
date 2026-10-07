"""Compare the package with the article's printed tables, cell by cell.

One implementation, used by tests/test_paper_numbers.py and notebooks/verify.ipynb, so
the suite and the notebook a reader opens cannot disagree about what "reproduces"
means.

The printed tables are tests/fixtures/article/table*.csv, kept as printed. A printed
value with d decimals is reproduced when the package's full-precision number ROUNDS to
it. Nineteen cells in Tables 2 and 3 were truncated in print instead (January's
modelled VMT is 278.367 B and prints as 278.36). Those are listed in TRUNCATED, and
each must truncate to its printed value and must not round to it, so the list cannot
go stale in either direction.

Needs nothing beyond the package's own dependencies: no network, no API key.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import costs, metrics, report
from .allocation import split_vmt

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

TABLE5 = {c: (c, 1) for c in ("Gas VMT (B)", "MPG", "Gallons (B)", "Gas Emissions (Mt CO2)",
                              "Electric VMT (B)", "Electricity (TWh)",
                              "Electricity Emissions (Mt CO2)", "Total Emissions (Mt CO2)",
                              "CO2 Saved (Mt CO2)")} | {"mi /kWh": ("mi / kWh", 1)}
# printed column -> (package column, multiplier to the printed unit)
TABLE6 = {"% EV VMT": ("% Electric", 100), "% Increase": ("% Increase", 100),
          "Battery Size Average (kWh)": ("Battery Size (kWh)", 1),
          "Battery Capacity (TWh)": ("Installed Battery (TWh)", 1),
          "Battery (Wh) /VMT": ("Battery Wh / VMT", 1),
          "Battery Cost $T": ("Battery Cost ($T)", 1),
          "$CAPEX /kg CO2": ("$ CAPEX / kg CO2", 1), "$CAPEX /EV Mile": ("$ CAPEX / EV Mile", 1),
          "$OPEX": ("OPEX ($B)", 1), "$OPEX /VMT": ("$ OPEX / VMT", 1),
          "$OPEX /kg CO2": ("$ OPEX / kg CO2", 1)}


def parse(printed: str) -> tuple[float | None, int]:
    """'$ 57.47' -> (57.47, 2); '59.4%' -> (59.4, 1); 'N/A' and '$-' -> (None, 0)."""
    text = str(printed).replace("$", "").replace("%", "").replace(",", "").strip()
    if text in ("N/A", "-", ""):
        return None, 0
    return float(text), len(text.split(".")[1]) if "." in text else 0


def rounds_to(ours: float, printed: float, decimals: int) -> bool:
    return abs(ours - printed) <= 0.5 * 10**-decimals + 1e-9


def truncates_to(ours: float, printed: float, decimals: int) -> bool:
    scale = 10**decimals
    return abs(math.copysign(math.floor(abs(ours) * scale + 1e-9) / scale, ours) - printed) < 1e-9


def printed_table(article_dir: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(Path(article_dir) / f"{name}.csv", dtype=str, keep_default_na=False)


def _scenario_cells(printed: pd.DataFrame, scen: pd.DataFrame, columns: dict):
    if list(printed["Vehicle Type"]) != list(scen["Vehicle Type"]):
        raise ValueError("printed rows and package rows are not in the same order")
    cells = []
    for i, r in printed.iterrows():
        key = f"{r['Scenario']}|{r['Vehicle Type']}"
        for col, (src, mult) in columns.items():
            value = float(scen.iloc[i][src])
            if r[col].strip() == "$-":  # the ICE row's battery cost: zero, printed as a dash
                if value != 0.0:
                    raise ValueError(f"{key} {col}: printed $-, package {value}")
                value = math.nan
            cells.append((key, col, value * mult, r[col]))
    return cells


def cells(name: str, fitted, config, article_dir: Path) -> list[tuple[str, str, float, str]]:
    """(row, column, package value in the printed unit, printed text) for one table."""
    printed = printed_table(article_dir, name)
    if name == "table1":
        ours = report.annual_table(fitted)
        cols = {"trips_b_yr": "Trips (B/year)", "avg_bin_dist_mi": "Average Bin Distance (miles)",
                "calculated_vmt_b": "Calculated VMT (B/year)"}
        return [(r["bin"], c, float(ours.iloc[i][v]), r[c])
                for i, r in printed.iterrows() for c, v in cols.items()]
    if name == "table2":
        modelled = fitted.vmt_miles_prenorm.sum(axis=1) / 1e9
        error = fitted.monthly_error_pct(prenorm=True)
        out = []
        for i, r in printed.iterrows():
            out += [(r["month"], "fhwa_vmt_b", float(fitted.fhwa_billion[i]), r["fhwa_vmt_b"]),
                    (r["month"], "model_vmt_b", float(modelled[i]), r["model_vmt_b"]),
                    (r["month"], "error_pct", float(error[i]), r["error_pct"])]
        return out
    if name == "table3":
        ours = report.table3(fitted, 50, config["paper_scenarios"]["households_millions"],
                             round_trip=config.round_trip)
        cols = {"avg_dist_mi": "Avg Dist (mi)", "trips_b_yr": "Trips (B/yr)",
                "trips_b_wk": "Trips (B/wk)", "trips_per_hh_wk": "Trips/HH/wk",
                "vmt_b_yr": "VMT (B/yr)", "ev_vmt_b_yr": "EV VMT (B/yr)",
                "gas_vmt_b_yr": "Gas VMT (B/yr)", "ev_pct_in_bin": "EV% in bin"}
        return [(r["bin"], c, float(ours.iloc[i][v]), r[c])
                for i, r in printed.iterrows() for c, v in cols.items()]
    if name in ("table5", "table6"):
        scen = costs.scenario_table(fitted, config)
        return _scenario_cells(printed, scen, TABLE5 if name == "table5" else TABLE6)
    raise ValueError(f"no comparison defined for {name!r}")


@dataclass
class Result:
    name: str
    rounded: int = 0
    truncated: int = 0
    not_applicable: int = 0
    misses: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.misses and (self.rounded + self.truncated) > 0

    def __str__(self) -> str:
        return (f"{self.name}: {self.rounded} cells round to print, {self.truncated} truncate "
                f"to print, {self.not_applicable} printed N/A or $-, "
                f"{len(self.misses)} do not reproduce")


def check(name: str, table_cells) -> Result:
    result = Result(name)
    for row, col, ours, printed in table_cells:
        value, d = parse(printed)
        if value is None:
            result.not_applicable += 1
            if not math.isnan(ours):
                result.misses.append(f"{name} {row} {col}: printed {printed!r}, ours {ours}")
            continue
        if (name, row, col) in TRUNCATED:
            if truncates_to(ours, value, d) and not rounds_to(ours, value, d):
                result.truncated += 1
            else:
                result.misses.append(f"{name} {row} {col}: listed as truncated, but ours "
                                     f"{ours!r} vs printed {printed!r} is not truncation-only")
        elif rounds_to(ours, value, d):
            result.rounded += 1
        else:
            result.misses.append(f"{name} {row} {col}: printed {printed!r}, ours {ours!r}")
    return result


def check_all(fitted, config, article_dir: Path) -> list[Result]:
    """Every printed cell of Tables 1-3 and 5-6. Table 4 holds inputs, not results."""
    return [check(n, cells(n, fitted, config, article_dir))
            for n in ("table1", "table2", "table3", "table5", "table6")]


def _row(scen, scenario, vehicle):
    return scen[(scen["Scenario"] == scenario) & (scen["Vehicle Type"] == vehicle)].iloc[0]


def _avg(scen, r):
    return _row(scen, "Average", costs.ldv_label(r))


def prose_numbers(fitted, config) -> list[tuple[str, str, float, str]]:
    """Numbers quoted in the article's prose that the package reproduces.

    (section, quoted text, package value in the quoted unit, printed number as text).
    """
    scen = costs.scenario_table(fitted, config)
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
