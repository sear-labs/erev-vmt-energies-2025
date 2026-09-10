"""Load and validate config/base.yaml.

Validation is here rather than at the point of use because a typo in a YAML key
is otherwise a `KeyError` thousands of lines into a run, or -- worse -- a
silently defaulted value that changes a published number without failing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REQUIRED_TOP_LEVEL = (
    "year",
    "month_to_show",
    "round_trip",
    "ranges",
    "normalize_to_fhwa",
    "bin_bounds",
    "emissions",
    "battery",
    "fleet",
    "charging",
    "scenarios",
)

REQUIRED_NESTED = {
    "emissions": ("mpg_gas", "co2_per_gal", "ev_kwh_per_mi", "grid_g_per_kwh"),
    "battery": ("eta_mi_per_kwh", "pack_cost_per_kwh"),
    "fleet": ("avg_driver_miles",),
    "charging": (
        "charges_per_week",
        "level_order",
        "acs_mapping",
        "weights_source",
        "published_fallback_weights",
    ),
}


@dataclass(frozen=True)
class Config:
    """The run's parameters. Frozen: no stage mutates configuration."""

    raw: dict
    path: Path

    def __getitem__(self, key):
        return self.raw[key]

    @property
    def year(self) -> int:
        return int(self.raw["year"])

    @property
    def ranges(self) -> list[int]:
        return [int(r) for r in self.raw["ranges"]]

    @property
    def round_trip(self) -> bool:
        return bool(self.raw["round_trip"])

    @property
    def normalize_to_fhwa(self) -> bool:
        return bool(self.raw["normalize_to_fhwa"])

    @property
    def month_to_show(self) -> int:
        return int(self.raw["month_to_show"])


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} did not parse to a mapping.")

    missing = [k for k in REQUIRED_TOP_LEVEL if k not in raw]
    if missing:
        raise ValueError(f"{path} is missing required keys: {missing}")

    for section, keys in REQUIRED_NESTED.items():
        absent = [k for k in keys if k not in raw[section]]
        if absent:
            raise ValueError(f"{path}: section '{section}' is missing keys: {absent}")

    if not 1 <= int(raw["month_to_show"]) <= 12:
        raise ValueError(f"{path}: month_to_show must be 1..12, got {raw['month_to_show']}")
    if not raw["ranges"]:
        raise ValueError(f"{path}: ranges must list at least one electric range.")
    if any(float(r) <= 0 for r in raw["ranges"]):
        raise ValueError(f"{path}: every range must be positive, got {raw['ranges']}")

    ladder = raw["charging"]["charges_per_week"]
    order = raw["charging"]["level_order"]
    if set(order) != set(ladder):
        raise ValueError(
            f"{path}: charging.level_order {sorted(order)} does not match "
            f"charges_per_week keys {sorted(ladder)}. The Low and More scenarios "
            "shift along level_order, so a level missing from it is silently unreachable."
        )
    unknown = set(raw["charging"]["acs_mapping"]) - set(ladder)
    if unknown:
        raise ValueError(
            f"{path}: acs_mapping names charging levels with no charges_per_week entry: "
            f"{sorted(unknown)}"
        )

    source = raw["charging"]["weights_source"]
    if source not in ("published_fallback", "acs_b25032"):
        raise ValueError(
            f"{path}: charging.weights_source must be 'published_fallback' or "
            f"'acs_b25032', got {source!r}"
        )
    fallback = raw["charging"]["published_fallback_weights"]
    if abs(sum(fallback.values()) - 1.0) > 1e-9:
        raise ValueError(
            f"{path}: published_fallback_weights must sum to 1.0, got {sum(fallback.values())}"
        )

    for label, bounds in raw["bin_bounds"].items():
        if len(bounds) != 2 or bounds[0] >= bounds[1]:
            raise ValueError(f"{path}: bin_bounds[{label!r}] must be [lo, hi] with lo < hi.")

    return Config(raw=raw, path=path)
