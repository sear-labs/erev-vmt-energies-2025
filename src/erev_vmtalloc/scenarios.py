"""Charging-frequency scenarios.

Households are placed on a ladder of charging situations -- from `none` to
`everyday` -- weighted by ACS B25032 tenure and units-in-structure counts. A
scenario turns those weights into a fleet-average charges-per-week, which caps
how many electric miles the fleet can drive in a year.

    Base_EachTrip   no cap: every trip starts on a full battery
    Normal          ACS weights as mapped
    Low             every household shifted one step DOWN the ladder
    More            every household shifted one step UP the ladder

The cap is fleet-wide and is applied by scaling electric miles down
proportionally across bins when it binds. It frequently does not bind -- see
README, "Stated residuals".
"""

from __future__ import annotations

import math

WEEKS_PER_YEAR = 52


def level_weights_from_acs(acs_counts: dict[str, float], config) -> dict[str, float]:
    """Map ACS tenure x units counts onto charging levels, normalized to 1.

    Raises if the mapping matches nothing, rather than falling back to a
    default weight vector. A silent fallback here changes the published
    scenario numbers while the run still reports success.
    """
    mapping = config["charging"]["acs_mapping"]
    weights = {level: 0.0 for level in config["charging"]["charges_per_week"]}

    matched_keys: set[str] = set()
    for level, specs in mapping.items():
        for spec in specs:
            key = f"{spec['tenure']}|{spec['units']}"
            if key in acs_counts:
                weights[level] += acs_counts[key]
                matched_keys.add(key)

    unmatched = [
        f"{s['tenure']}|{s['units']}"
        for specs in mapping.values()
        for s in specs
        if f"{s['tenure']}|{s['units']}" not in acs_counts
    ]
    if unmatched:
        raise ValueError(
            "ACS snapshot has no entry for these configured categories: "
            f"{unmatched}. Available keys start: {sorted(acs_counts)[:5]}. "
            "The ACS label format has changed, or acs_mapping in config is stale."
        )

    total = sum(weights.values())
    if total <= 0:
        raise ValueError("ACS level weights summed to zero; the mapping matched no counts.")
    return {level: w / total for level, w in weights.items() if w > 0}


def shift_weights(weights: dict[str, float], delta: int, config) -> dict[str, float]:
    """Move every household `delta` steps along the charging ladder, clamped."""
    order = list(config["charging"]["level_order"])
    shifted = {level: 0.0 for level in config["charging"]["charges_per_week"]}
    for level, weight in weights.items():
        index = min(max(order.index(level) + delta, 0), len(order) - 1)
        shifted[order[index]] += weight
    return {level: w for level, w in shifted.items() if w > 0}


def base_level_weights(acs_counts: dict[str, float], config) -> dict[str, float]:
    """Weights over charging levels for the `Normal` scenario.

    Which source is used is a configuration choice, not a runtime accident:

        published_fallback  the hardcoded vector the published run used
        acs_b25032          derived from the ACS snapshot, as the notebook intended

    See README, "Scenario weights", for why these differ.
    """
    source = config["charging"].get("weights_source", "acs_b25032")
    if source == "acs_b25032":
        return level_weights_from_acs(acs_counts, config)
    if source == "published_fallback":
        weights = dict(config["charging"]["published_fallback_weights"])
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"published_fallback_weights must sum to 1.0, got {total}")
        return weights
    raise ValueError(
        f"Unknown charging.weights_source {source!r}. "
        "Expected 'published_fallback' or 'acs_b25032'."
    )


def charges_per_week(scenario: str, acs_counts: dict[str, float], config) -> float:
    """Fleet-average charges per week under one scenario. inf for the base case."""
    if scenario == "Base_EachTrip":
        return math.inf

    base = base_level_weights(acs_counts, config)
    deltas = {"Normal": 0, "Low": -1, "More": +1}
    if scenario not in deltas:
        raise ValueError(
            f"Unknown scenario {scenario!r}. Known: Base_EachTrip, {', '.join(deltas)}"
        )
    weights = shift_weights(base, deltas[scenario], config) if deltas[scenario] else base

    ladder = config["charging"]["charges_per_week"]
    return sum(ladder[level] * weight for level, weight in weights.items())


def annual_ev_budget_miles(
    scenario: str,
    electric_range: float,
    n_vehicles: float,
    acs_counts: dict[str, float],
    config,
) -> float | None:
    """Annual fleet-wide cap on electric miles, or None when uncapped.

    A household that charges `c` times a week can drive at most `c * R` electric
    miles a week, since each charge buys one range's worth.
    """
    cpw = charges_per_week(scenario, acs_counts, config)
    if math.isinf(cpw):
        return None
    return cpw * electric_range * WEEKS_PER_YEAR * n_vehicles
