"""Input data: fetch once from the federal APIs, then read the frozen snapshot.

The published notebook called the BTS and Census APIs at run time. That makes
the paper's inputs mutable -- a re-run next year silently gets different data,
and a re-run with no network gets nothing at all. Part 1 rule 4 requires the
opposite, so the network path lives in `fetch_*` and is exercised only by
`scripts/fetch_sources.py`. Everything else reads `data/raw/`.

Bin labels use an ASCII hyphen ("0-1"), not the en-dash the notebook used.
The en-dash round-trips badly through Windows consoles and CSV readers, and
the label is a join key between the BTS response, the config bounds and the
results tables -- three places for one mojibake to break a merge quietly.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import requests

BTS_URL = "https://data.bts.gov/resource/w96p-f2qv.json"
ACS_VARS_URL = "https://api.census.gov/data/2024/acs/acs1/variables.json"
ACS_DATA_URL = "https://api.census.gov/data/2024/acs/acs1"
ACS_TABLE = "B25032"

# Accepted values of the BTS "level" column, lowercased.
LEVEL_OK = ("national", "nation", "n")

# BTS response column -> trip-distance bin label.
BIN_LABEL = {
    "trips_1": "0-1",
    "trips_1_3": "1-3",
    "trips_3_5": "3-5",
    "trips_5_10": "5-10",
    "trips_10_25": "10-25",
    "trips_25_50": "25-50",
    "trips_50_100": "50-100",
    "trips_100_250": "100-250",
    "trips_250_500": "250-500",
    "trips_500": "500+",
}

# Bins in increasing distance order. Explicit, because sorting these labels as
# strings puts "100-250" before "1-3".
BIN_ORDER = list(BIN_LABEL.values())


class SnapshotMissing(FileNotFoundError):
    """Raised when a required snapshot has not been fetched.

    Carries the remedy, because the standard's Part 2b rule applies to any
    designed failure: whoever meets the error must find the fix beside it.
    """


def _get_json(url: str, params: dict | None = None, timeout: int = 60):
    """GET and parse JSON, failing usefully when the body is not JSON.

    The Census API answers a keyless data request with HTTP 200 and an HTML
    "Missing Key" page. `raise_for_status()` passes and `.json()` then raises a
    JSONDecodeError pointing at column 1, which says nothing about the cause.
    """
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    body = response.text.lstrip()
    if not body.startswith(("{", "[")):
        snippet = " ".join(body[:200].split())
        raise RuntimeError(
            f"{url} returned HTTP {response.status_code} with a non-JSON body. "
            f"First 200 characters: {snippet!r}"
        )
    return response.json()


# --------------------------------------------------------------------------
# Fetch (network). Called only by scripts/fetch_sources.py.
# --------------------------------------------------------------------------


def fetch_bts_trips(year: int) -> pd.DataFrame:
    """National monthly trip counts by distance bin, for one year.

    Returns a 12-row frame: a `month` column plus one column per bin label.
    """
    sample = _get_json(BTS_URL, {"$limit": 1})
    if not sample:
        raise RuntimeError(f"BTS endpoint {BTS_URL} returned 0 rows.")
    columns = set(sample[0].keys())

    trip_columns = [c for c in BIN_LABEL if c in columns]
    missing = set(BIN_LABEL) - set(trip_columns)
    if missing:
        raise RuntimeError(
            f"BTS response is missing expected trip columns: {sorted(missing)}. "
            "The dataset schema has changed; the bin mapping in sources.py needs review."
        )

    has_month = "month" in columns
    if has_month:
        select_parts = ["month"]
        group_order = "month"
    else:
        select_parts = ["date_trunc_ym(date) as ym"]
        group_order = "ym"
    select_parts += [f"sum({c}) as {c}" for c in trip_columns]

    where_parts = [
        f"date >= '{year}-01-01T00:00:00.000'",
        f"date <  '{year + 1}-01-01T00:00:00.000'",
    ]
    if "level" in columns:
        where_parts.append(
            "lower(level) in (" + ", ".join(repr(v) for v in LEVEL_OK) + ")"
        )

    params = {
        "$select": ", ".join(select_parts),
        "$where": " AND ".join(where_parts),
        "$group": group_order,
        "$order": group_order,
        "$limit": 5000,
    }
    rows = _get_json(BTS_URL, params)
    if not rows:
        raise RuntimeError(
            f"BTS aggregation for {year} returned 0 rows with params {params!r}."
        )

    frame = pd.DataFrame(rows)
    if has_month:
        frame["month"] = pd.to_numeric(frame["month"], errors="coerce").astype("Int64")
        frame["year"] = year
    else:
        frame["ym"] = pd.to_datetime(frame["ym"], errors="coerce").dt.tz_localize(None)
        frame["month"] = frame["ym"].dt.month
        frame["year"] = frame["ym"].dt.year

    years = frame["year"].dropna().unique().tolist()
    if years != [year]:
        raise RuntimeError(f"BTS returned years {years}, expected [{year}].")

    for column in trip_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    trips = (
        frame[["month"] + trip_columns]
        .rename(columns=BIN_LABEL)
        .sort_values("month")
        .reset_index(drop=True)
    )
    return trips[["month"] + BIN_ORDER]


def fetch_acs_units(api_key: str | None = None) -> dict[str, float]:
    """ACS B25032 counts, keyed by "<tenure>|<units in structure>".

    Args:
        api_key: a Census API key. Required as of 2026-09; the data endpoint
            answers keyless requests with an HTML "Missing Key" page. Falls
            back to the CENSUS_API_KEY environment variable. Free from
            https://api.census.gov/data/key_signup.html -- put it in `.env`,
            which is gitignored, and never in config or a commit.

    Any failure raises. The notebook fell back to a hardcoded weight vector and
    only warned; a warning in a long run is not read, and the result was a
    different published number produced under the same command. A scenario
    weight is an input, and a substituted input has to be loud.
    """
    api_key = api_key or os.environ.get("CENSUS_API_KEY")
    meta = _get_json(ACS_VARS_URL)
    variables = meta.get("variables", {})
    if not variables:
        raise RuntimeError(f"ACS variables endpoint {ACS_VARS_URL} returned no variables.")

    # Labels look like:
    #   Estimate!!Total:!!Owner-occupied housing units:!!1, detached
    # Split on "!!" and match on parts rather than substrings: the notebook
    # searched for "Owner occupied" and "!!Estimate" as substrings and matched
    # nothing, because the real text is "Owner-occupied housing units" and the
    # label *starts* with "Estimate!!".
    wanted: dict[str, str] = {}
    for name, spec in variables.items():
        if not name.startswith(ACS_TABLE + "_"):
            continue
        parts = [p.strip().rstrip(":").strip() for p in spec.get("label", "").split("!!")]
        if len(parts) != 4 or parts[0] != "Estimate":
            continue  # totals and subtotals, not leaf categories
        tenure_text = parts[2]
        if tenure_text.startswith("Owner-occupied"):
            tenure = "owner"
        elif tenure_text.startswith("Renter-occupied"):
            tenure = "renter"
        else:
            continue
        wanted[name] = f"{tenure}|{parts[3]}"

    if not wanted:
        raise RuntimeError(
            f"No {ACS_TABLE} estimate variables found at {ACS_VARS_URL}. "
            "The table or its label format has changed."
        )

    names = sorted(wanted)
    if not api_key:
        raise RuntimeError(
            "A Census API key is required to fetch ACS data. Get one free at "
            "https://api.census.gov/data/key_signup.html, then either set "
            "CENSUS_API_KEY in your environment or put it in a .env file "
            "(gitignored). Note that the paper's published numbers do NOT need "
            "this: config/base.yaml uses charging.weights_source=published_fallback, "
            "which requires no ACS call. See README, 'Known defect'."
        )
    params = {"get": "NAME," + ",".join(names), "for": "us:1", "key": api_key}
    data = _get_json(ACS_DATA_URL, params)
    header, values = data[0], data[1]
    record = dict(zip(header, values, strict=True))

    counts: dict[str, float] = {}
    for name in names:
        raw = record.get(name)
        if raw in (None, "", "null"):
            continue
        counts[wanted[name]] = float(raw)
    if not counts:
        raise RuntimeError(f"ACS returned no usable values for {ACS_TABLE}.")
    return counts


# --------------------------------------------------------------------------
# Snapshot write / read.
# --------------------------------------------------------------------------


def write_snapshot(path: Path, payload, *, source_url: str, description: str) -> None:
    """Write a snapshot plus the sidecar that says where it came from and when."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(text, encoding="utf-8")

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    sidecar = path.with_suffix(path.suffix + ".meta.yaml")
    sidecar.write_text(
        "# Provenance for {name}. Written by scripts/fetch_sources.py.\n"
        "# This file is an INPUT (Part 1 rule 4): it is never edited by an\n"
        "# analysis stage. Re-fetching is a deliberate act with a new date.\n"
        "source_url: {url}\n"
        "description: {desc}\n"
        "fetched_utc: {when}\n"
        "sha256: {digest}\n".format(
            name=path.name,
            url=source_url,
            desc=description,
            when=_dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            digest=digest,
        ),
        encoding="utf-8",
    )


def _require(path: Path, what: str) -> Path:
    if not path.exists():
        raise SnapshotMissing(
            f"{what} snapshot not found at {path}.\n"
            "This repository reads frozen inputs, not live APIs. Run:\n"
            "    python scripts/fetch_sources.py\n"
            "once, with network access, to create it. Re-running it replaces the\n"
            "paper's inputs with today's data -- see README, 'Refreshing inputs'."
        )
    return path


def load_bts_trips(raw_dir: Path, year: int) -> pd.DataFrame:
    """Read the frozen BTS snapshot as a 12-row frame of trips per bin."""
    path = _require(raw_dir / f"bts_trips_{year}.json", "BTS trips")
    trips = pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
    return trips[["month"] + BIN_ORDER].sort_values("month").reset_index(drop=True)


def load_acs_units(raw_dir: Path) -> dict[str, float]:
    """Read the frozen ACS B25032 snapshot."""
    path = _require(raw_dir / "acs_b25032.json", "ACS B25032")
    return json.loads(path.read_text(encoding="utf-8"))


def load_fhwa_vmt(raw_dir: Path, year: int) -> dict[int, float]:
    """Read FHWA monthly VMT targets, in billions of miles, keyed by month."""
    path = _require(raw_dir / f"fhwa_vmt_{year}.csv", "FHWA monthly VMT")
    frame = pd.read_csv(path, comment="#")
    return {
        int(m): float(v)
        for m, v in zip(frame["month"], frame["vmt_billion_miles"], strict=True)
    }
