#!/usr/bin/env python
"""No committed file may carry an absolute path from the machine that wrote it.

    python scripts/check_no_machine_paths.py

Taken from ``sear-labs/sav-osemosys-trd-2019`` (also in
``water-energy-coopt-scs-2021``), not rewritten, and widened in three places for what this
repository ships. This repository is heading for public release and a Zenodo DOI, and a
home-directory path in a committed file publishes a username. One was here: this
project's own ``CLAUDE.md`` named a co-author's home folder until 2026-10-07. (Not quoted
here, because this check would flag the docstring if it were.)

Three things this check exists to get right, each found the hard way:

**Enumerate with ``git ls-files -z``, not a whitespace split.** A path containing a
space breaks apart under ``.split()`` into fragments that do not exist; ``is_file()``
then returns False for each and the file is skipped with no message at all. This
repository does ship such paths (``notebooks/fall-2025/Calculations Check_final.xlsx``),
and every listed path is asserted to resolve rather than merely counted, because a skip
and a scan look identical from a summary line.

**Read binary files too, including inside containers.** ``grep -I`` (and naive UTF-8
decoding) skips anything that does not look like text. An ``.xlsx`` is a zip of XML, so a
path written into it by the program that saved it is invisible to a byte scan of the
compressed file. That is not hypothetical here: Excel records the folder a workbook
was last saved in (``absPath`` in ``xl/workbook.xml``), and both imported workbooks
carried one. So every zip and gzip member is decompressed and scanned as well.

**Prove the pattern can match before trusting that it did not.** A regex built to
match one-or-two literal backslashes is exactly the kind of thing that silently
matches nothing if a single character is wrong. ``_probe`` builds a known match for
EACH pattern with the same machinery the real patterns use and asserts it fires,
every run, before the real sweep is trusted.

Widened here, beyond the original's home-directory patterns:

- any drive-letter absolute path (one of the workbooks named a student's own drive,
  which no home-directory pattern matches);
- a SharePoint/OneDrive personal-site URL, which carries an account name the way a
  home directory does (the other workbook named one).

Limit, stated rather than implied: this reads raw bytes plus zip and gzip members. A
path inside a zlib-compressed PDF stream or a PNG ``zTXt`` chunk would not be seen.
Neither format is shipped with such content today; the PNGs are matplotlib output.
"""
from __future__ import annotations

import gzip
import io
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Built with chr(92), never a literal backslash in source: a Windows path written
# directly into a Python string is a known trap - `\U` and `\1` are escapes, not the
# characters they look like, and one of the two fails silently. re.escape() on the
# assembled separator is what keeps this from becoming another variant of the same bug.
_BS = re.escape(chr(92)).encode()

_PATTERNS = {
    "windows home": re.compile(rb"[A-Za-z]:" + _BS + rb"+Users" + _BS + rb"+[A-Za-z0-9_.-]+"),
    "linux home": re.compile(rb"/home/[a-z][a-z0-9_-]*/"),
    "macos home": re.compile(rb"/Users/[A-Za-z0-9_.-]+/"),
    "drive-letter path": re.compile(
        rb"(?<![A-Za-z0-9])[A-Za-z]:" + _BS + rb"+[A-Za-z0-9 _.()&-]+" + _BS
    ),
    "personal sharepoint": re.compile(rb"-my\.sharepoint\.com/personal/[A-Za-z0-9_.-]+"),
}

# Each probe is assembled from pieces so that this file's own source does not match
# the patterns it defines (the sweep reads this file too).
_PROBES = {
    "windows home": "C:" + chr(92) + "Users" + chr(92) + "probe" + chr(92) + "leak.txt",
    "linux home": "/" + "home/probe/leak.txt",
    "macos home": "/" + "Users/probe/leak.txt",
    "drive-letter path": "F:" + chr(92) + "Some Folder" + chr(92) + "leak.xlsx",
    "personal sharepoint": "https://org-my" + ".sharepoint.com/" + "personal/probe/Documents/",
}


def _probe() -> None:
    """Each pattern must be shown capable of matching before its silence means anything."""
    assert set(_PROBES) == set(_PATTERNS), "every pattern needs its own probe"
    for name, pattern in _PATTERNS.items():
        assert pattern.search(_PROBES[name].encode()), (
            f"the {name!r} pattern does not match its own probe string - "
            "fix the pattern before trusting any 'no matches' result"
        )


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    return [f for f in out.stdout.split("\0") if f]


def _prove_the_distinction_matters() -> None:
    """Demonstrate the whitespace-split failure on a synthetic list, so the -z
    enumeration below is known to be fixing a real failure mode."""
    synthetic = ["a.csv", "figures/gas share.png", "b.csv"]
    naive = " ".join(synthetic).split()
    assert "figures/gas share.png" not in naive, (
        "the synthetic spaced path survived a whitespace split - the demonstration "
        "itself is broken, not just the thing it demonstrates"
    )
    assert "figures/gas" in naive and "share.png" in naive, (
        "expected the whitespace split to fragment the spaced path into two pieces"
    )


def _every_listed_path_resolves(names: list[str]) -> None:
    """A path `git ls-files -z` names but the filesystem does not have means
    enumeration and filesystem disagree; silently continuing is the whitespace-split
    failure by another route."""
    for name in names:
        assert (ROOT / name).is_file(), (
            f"{name!r} was listed by git but does not resolve to a file"
        )


def _blobs(name: str, raw: bytes) -> list[tuple[str, bytes]]:
    """The file's own bytes, plus every member of a zip or gzip container."""
    out = [(name, raw)]
    if raw[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            out += [(f"{name}!{m}", z.read(m)) for m in z.namelist()]
    elif raw[:2] == b"\x1f\x8b":
        try:
            out.append((f"{name}!gunzip", gzip.decompress(raw)))
        except OSError:
            pass  # not actually gzip; the raw-bytes scan still covers it
    return out


def sweep() -> str:
    _probe()
    _prove_the_distinction_matters()
    names = _tracked_files()
    assert names, "git listed no tracked files at all"
    _every_listed_path_resolves(names)

    hits: list[tuple[str, str, bytes]] = []
    members = 0
    for name in names:
        for label, blob in _blobs(name, (ROOT / name).read_bytes()):
            members += 1
            for kind, pattern in _PATTERNS.items():
                for match in set(pattern.findall(blob)):
                    hits.append((label, kind, match))

    assert not hits, "machine path(s) found in committed files:\n" + "\n".join(
        f"  {label} [{kind}]: {match.decode('utf-8', 'replace')}"
        for label, kind, match in hits
    )
    return (f"{len(names)} tracked files ({members} files and container members) swept, "
            "0 machine paths found")


def main() -> int:
    try:
        detail = sweep()
    except AssertionError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print(f"ok   {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
