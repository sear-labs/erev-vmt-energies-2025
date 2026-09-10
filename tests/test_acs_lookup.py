"""Pins the ACS label defect that put fallback weights into the paper.

Offline: the label strings below are copied verbatim from
api.census.gov/data/2024/acs/acs1/variables.json, retrieved 2026-09-10.

The published notebook selected B25032 variables with

    if side in lab and pattern in lab and ("!!Estimate" in lab)

where `side` was "Owner occupied"/"Renter occupied" and `pattern` was one of
"1, detached", "2 apartments", .... That predicate matches zero of the real
labels, for three independent reasons, so the lookup returned an empty list and
the notebook fell through to a hardcoded weight vector with only a warning.

The first test below shows the predicate failing. The second shows the
replacement working. Together they are the evidence for the README's "Known
defect" section, and they make the regression impossible to reintroduce.
"""

from __future__ import annotations

import pytest

from erev_vmtalloc import scenarios

# Verbatim subset of the real B25032 labels.
REAL_LABELS = {
    "B25032_001E": "Estimate!!Total:",
    "B25032_002E": "Estimate!!Total:!!Owner-occupied housing units:",
    "B25032_003E": "Estimate!!Total:!!Owner-occupied housing units:!!1, detached",
    "B25032_004E": "Estimate!!Total:!!Owner-occupied housing units:!!1, attached",
    "B25032_005E": "Estimate!!Total:!!Owner-occupied housing units:!!2",
    "B25032_006E": "Estimate!!Total:!!Owner-occupied housing units:!!3 or 4",
    "B25032_007E": "Estimate!!Total:!!Owner-occupied housing units:!!5 to 9",
    "B25032_008E": "Estimate!!Total:!!Owner-occupied housing units:!!10 to 19",
    "B25032_009E": "Estimate!!Total:!!Owner-occupied housing units:!!20 to 49",
    "B25032_010E": "Estimate!!Total:!!Owner-occupied housing units:!!50 or more",
    "B25032_013E": "Estimate!!Total:!!Renter-occupied housing units:",
    "B25032_014E": "Estimate!!Total:!!Renter-occupied housing units:!!1, detached",
    "B25032_015E": "Estimate!!Total:!!Renter-occupied housing units:!!1, attached",
    "B25032_016E": "Estimate!!Total:!!Renter-occupied housing units:!!2",
    "B25032_017E": "Estimate!!Total:!!Renter-occupied housing units:!!3 or 4",
    "B25032_021E": "Estimate!!Total:!!Renter-occupied housing units:!!50 or more",
}


def _published_predicate(label: str, side: str, pattern: str) -> bool:
    """The notebook's selector, reproduced exactly."""
    return side in label and pattern in label and ("!!Estimate" in label)


def test_published_selector_matches_nothing():
    """The defect itself: zero matches across every side/pattern combination."""
    sides = ["Owner occupied", "Renter occupied"]
    patterns = [
        "1, detached",
        "1, attached",
        "2 apartments",
        "3 or 4 apartments",
        "5 to 9",
        "10 to 19",
        "20 to 49",
        "50 or more",
    ]
    matched = [
        name
        for label in REAL_LABELS.values()
        for side in sides
        for pattern in patterns
        if _published_predicate(label, side, pattern)
        for name in [label]
    ]
    assert matched == [], f"Expected the published selector to match nothing, got {matched}"


@pytest.mark.parametrize(
    "label,reason",
    [
        (
            "Estimate!!Total:!!Owner-occupied housing units:!!1, detached",
            "tenure text is 'Owner-occupied housing units', not 'Owner occupied'",
        ),
    ],
)
def test_each_failure_reason_independently(label, reason):
    assert "Owner occupied" not in label, reason
    assert "!!Estimate" not in label, "label starts with 'Estimate!!'; there is no '!!Estimate'"
    assert "2 apartments" not in label, "unit categories are '2' and '3 or 4', not '... apartments'"


def _parse(labels: dict[str, str]) -> dict[str, str]:
    """The replacement selector from sources.fetch_acs_units, isolated."""
    wanted = {}
    for name, label in labels.items():
        parts = [p.strip().rstrip(":").strip() for p in label.split("!!")]
        if len(parts) != 4 or parts[0] != "Estimate":
            continue
        if parts[2].startswith("Owner-occupied"):
            tenure = "owner"
        elif parts[2].startswith("Renter-occupied"):
            tenure = "renter"
        else:
            continue
        wanted[name] = f"{tenure}|{parts[3]}"
    return wanted


def test_replacement_selector_finds_the_leaf_categories():
    parsed = _parse(REAL_LABELS)
    assert parsed["B25032_003E"] == "owner|1, detached"
    assert parsed["B25032_016E"] == "renter|2"
    assert parsed["B25032_021E"] == "renter|50 or more"
    # Totals and tenure subtotals must not be counted as categories.
    assert "B25032_001E" not in parsed
    assert "B25032_002E" not in parsed
    assert "B25032_013E" not in parsed


def test_config_mapping_matches_real_label_text(config):
    """Every category named in config must exist in the real ACS labels.

    This is the guard that would have caught the original bug at config-load
    time rather than at a warning nobody read.
    """
    available = set(_parse(REAL_LABELS).values())
    for level, specs in config["charging"]["acs_mapping"].items():
        for spec in specs:
            key = f"{spec['tenure']}|{spec['units']}"
            assert key in available, (
                f"config acs_mapping[{level}] names {key!r}, which is not a real "
                f"B25032 category. Available: {sorted(available)}"
            )


def test_published_fallback_reproduces_the_paper_weights(config):
    """The vector the paper's scenarios actually used."""
    weights = scenarios.base_level_weights({}, config)
    assert weights == {"garage": 0.45, "driveway": 0.25, "work": 0.20, "weekly": 0.10}
    assert scenarios.charges_per_week("Normal", {}, config) == pytest.approx(4.65)
    assert scenarios.charges_per_week("Low", {}, config) == pytest.approx(3.25)
    assert scenarios.charges_per_week("More", {}, config) == pytest.approx(5.95)
