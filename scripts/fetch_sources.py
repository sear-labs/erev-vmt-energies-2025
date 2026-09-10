"""Fetch the federal inputs once and freeze them into data/raw/.

This is the only script in the repository that touches the network. Running it
replaces the paper's inputs with whatever the APIs serve today, so it is not
part of `run_all.py` and is not run by CI.

    python scripts/fetch_sources.py            # fetch if absent
    python scripts/fetch_sources.py --refresh  # re-fetch and overwrite
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from erev_vmtalloc import sources  # noqa: E402


def _write_manifest(raw_dir: Path) -> None:
    """Record a hash of every raw input, so a change to one is visible."""
    lines = []
    for path in sorted(raw_dir.iterdir()):
        if path.name in {"MANIFEST.sha256", ".gitkeep"} or path.is_dir():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    (raw_dir / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote MANIFEST.sha256 ({len(lines)} inputs)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-fetch even if a snapshot already exists (changes the paper's inputs)",
    )
    args = parser.parse_args()

    raw_dir = REPO_ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    bts_path = raw_dir / f"bts_trips_{args.year}.json"
    if bts_path.exists() and not args.refresh:
        print(f"BTS snapshot already present: {bts_path.name} (use --refresh to replace)")
    else:
        print(f"Fetching BTS national monthly trips by distance for {args.year} ...")
        trips = sources.fetch_bts_trips(args.year)
        sources.write_snapshot(
            bts_path,
            trips.to_dict(orient="records"),
            source_url=sources.BTS_URL,
            description=(
                f"BTS Trips by Distance, national level, monthly sums for {args.year}, "
                "by trip-distance bin."
            ),
        )
        print(f"  wrote {bts_path.name}: {len(trips)} months x {len(sources.BIN_ORDER)} bins")

    # ACS is OPTIONAL. The paper's numbers use charging.weights_source =
    # published_fallback, which needs no ACS call. Fetching it only enables the
    # corrected acs_b25032 path, and that needs a Census API key.
    acs_path = raw_dir / "acs_b25032.json"
    if acs_path.exists() and not args.refresh:
        print(f"ACS snapshot already present: {acs_path.name} (use --refresh to replace)")
    else:
        print(f"Fetching ACS {sources.ACS_TABLE} (tenure by units in structure) ...")
        try:
            counts = sources.fetch_acs_units()
        except RuntimeError as exc:
            print(f"  SKIPPED: {exc}")
            print(
                "  This does not block reproduction of the paper. It only leaves\n"
                "  charging.weights_source=acs_b25032 unavailable."
            )
        else:
            sources.write_snapshot(
                acs_path,
                counts,
                source_url=sources.ACS_DATA_URL,
                description=(
                    f"ACS 1-year table {sources.ACS_TABLE}, tenure by units in structure, "
                    "national totals. Used to weight the charging-frequency ladder."
                ),
            )
            print(f"  wrote {acs_path.name}: {len(counts)} tenure x units categories")

    _write_manifest(raw_dir)
    print("\nInputs frozen. `python scripts/run_all.py` now runs with no network.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
