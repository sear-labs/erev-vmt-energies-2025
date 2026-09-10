"""End to end: does one command produce the outputs, on a clean machine?

Part 1 rule 6. The clean machine matters more than the test count, so this
runs the real entry point in a subprocess with no network and writes into a
temporary directory rather than importing pieces of it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def run_output(tmp_path_factory):
    results = tmp_path_factory.mktemp("results")
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "run_all.py"), "--results", str(results)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 0, (
        f"run_all.py exited {completed.returncode}\n"
        f"--- stdout ---\n{completed.stdout}\n--- stderr ---\n{completed.stderr}"
    )
    return results, completed


def test_run_all_writes_tables_and_figures(run_output):
    results, _ = run_output
    tables = sorted((results / "tables").glob("*.csv"))
    figures = sorted((results / "figures").glob("*.png"))
    assert tables, "run_all.py produced no tables"
    assert figures, "run_all.py produced no figures"
    for figure in figures:
        assert figure.stat().st_size > 1000, f"{figure.name} looks empty"


def test_summary_table_is_sane(run_output):
    results, _ = run_output
    summary = pd.read_csv(results / "tables" / "range_summary_base.csv")
    assert list(summary["Range (mi)"]) == [50, 75, 100, 125, 150]
    assert summary["EV share (%)"].between(0, 100).all()
    assert (summary["EV VMT (B)"] > 0).all()
    assert (summary["Battery size (kWh)"] > 0).all()
    # Totals must balance to the FHWA annual figure at every range.
    total = summary["EV VMT (B)"] + summary["Gas VMT (B)"]
    assert total.round(1).nunique() == 1, "Total VMT is not constant across ranges"


def test_run_needs_no_network(run_output):
    """A run that silently reached the internet would not be reproducible."""
    _, completed = run_output
    assert "Fetching" not in completed.stdout, (
        "run_all.py appears to have fetched from the network; it must read "
        "only the frozen snapshots in data/raw/."
    )


def test_inputs_are_not_modified(run_output):
    """Part 1 rule 4: no stage writes back to data/raw/."""
    import hashlib

    manifest = (REPO_ROOT / "data" / "raw" / "MANIFEST.sha256").read_text(encoding="utf-8")
    for line in manifest.strip().splitlines():
        digest, name = line.split("  ", 1)
        path = REPO_ROOT / "data" / "raw" / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == digest, (
            f"{name} has changed since it was frozen. Inputs are immutable; if the "
            "change was deliberate, re-run scripts/fetch_sources.py --refresh."
        )
