"""Shared fixtures. One fit per session; it is deterministic and not cheap."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# A bare clone, before `pip install -e .`, cannot import the package, and the suite
# would stop at collection instead of giving a result. Put src/ on the path only in
# that case; after an install the import succeeds and this does nothing.
try:
    import erev_vmtalloc  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from erev_vmtalloc import sources  # noqa: E402
from erev_vmtalloc.allocation import fit_bin_distances  # noqa: E402
from erev_vmtalloc.config import load_config  # noqa: E402

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
