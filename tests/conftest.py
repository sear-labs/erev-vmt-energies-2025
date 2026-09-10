"""Shared fixtures. One fit per session; it is deterministic and not cheap."""

from __future__ import annotations

from pathlib import Path

import pytest

from erev_vmtalloc import sources
from erev_vmtalloc.allocation import fit_bin_distances
from erev_vmtalloc.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"


@pytest.fixture(scope="session")
def config():
    return load_config(REPO_ROOT / "config" / "base.yaml")


@pytest.fixture(scope="session")
def fitted(config):
    trips = sources.load_bts_trips(RAW_DIR, config.year)
    fhwa = sources.load_fhwa_vmt(RAW_DIR, config.year)
    return fit_bin_distances(
        trips, fhwa, config["bin_bounds"], normalize_to_fhwa=config.normalize_to_fhwa
    )
