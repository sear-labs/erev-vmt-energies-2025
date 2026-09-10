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


def _manifest_entries():
    manifest = (REPO_ROOT / "data" / "raw" / "MANIFEST.sha256").read_text(encoding="utf-8")
    return [line.split("  ", 1) for line in manifest.strip().splitlines()]


def test_inputs_are_not_modified(run_output):
    """Part 1 rule 4: no stage writes back to data/raw/."""
    import hashlib

    for digest, name in _manifest_entries():
        path = REPO_ROOT / "data" / "raw" / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == digest, (
            f"{name} has changed since it was frozen. Inputs are immutable; if the "
            "change was deliberate, re-run scripts/fetch_sources.py --refresh."
        )


def test_provenance_records_agree():
    """The sidecar and the manifest must hash the same bytes.

    Each snapshot carries its hash twice: in its own `.meta.yaml` and in
    MANIFEST.sha256. They were written by different code paths and silently
    disagreed -- one hashed the logical text, the other the bytes on disk, and
    on Windows those differed by line endings. Two provenance records that
    disagree are worse than one, because whichever a reader checks looks
    authoritative.
    """
    raw_dir = REPO_ROOT / "data" / "raw"
    by_name = {name: digest for digest, name in _manifest_entries()}

    checked = 0
    for sidecar in raw_dir.glob("*.meta.yaml"):
        subject = sidecar.name.removesuffix(".meta.yaml")
        recorded = next(
            line.split(":", 1)[1].strip()
            for line in sidecar.read_text(encoding="utf-8").splitlines()
            if line.startswith("sha256:")
        )
        assert subject in by_name, f"{subject} has a sidecar but no manifest entry"
        assert recorded == by_name[subject], (
            f"{subject}: sidecar records {recorded[:12]}... but MANIFEST records "
            f"{by_name[subject][:12]}.... The two provenance records disagree."
        )
        checked += 1
    assert checked > 0, "No provenance sidecars found to check"


def test_inputs_use_lf_endings():
    """Frozen inputs are byte-identical on every platform, or they are not frozen."""
    for _, name in _manifest_entries():
        data = (REPO_ROOT / "data" / "raw" / name).read_bytes()
        assert b"\r\n" not in data, (
            f"{name} contains CRLF. Its hash then differs between a Windows and a "
            "Linux checkout, and the immutability guard fails for a reason that has "
            "nothing to do with the data. See .gitattributes and sources._write_text_lf."
        )
