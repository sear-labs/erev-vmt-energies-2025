#!/usr/bin/env python
"""Import the Fall 2025 notebook and workbooks behind Tables 4-6 and Figures 1-13.

    python scripts/import_fall2025_evidence.py <folder holding the three originals>

Run once, on 2026-10-07, from the SEAR Labs shared drive copy (``EV Analysis/Fall
2025/Code`` and ``EV Analysis/Data``). The same three files sat in
``searlabtransfer/EV-Analysis`` at commit 042738c (``Fall_2025/``), byte-identical, before
that organisation was deleted. This script is kept so the import can be re-run and
checked by anyone who still has the originals; without them, the record it wrote
(``notebooks/fall-2025/PROVENANCE.json``) and ``tests/test_frozen_evidence.py`` are what
prove the committed copies are the originals.

What it does to each file, and nothing else:

- ``EV_Graphs_Updated_Finalist.ipynb``: copied byte for byte.
- the two ``Calculations Check_final*.xlsx`` workbooks: one element removed from
  ``xl/workbook.xml``. Excel records the folder a workbook was last saved in, as
  ``<x15ac:absPath url=...>`` inside an ``<mc:AlternateContent>`` wrapper. One workbook
  named a personal OneDrive folder and the other a student's own drive. Neither belongs
  in a public deposit, and the element is advisory: Excel rewrites it on every save and
  nothing reads it.
- ``Calculations Check_final - Copy.xlsx`` only: the text of ``<cp:lastModifiedBy>`` in
  ``docProps/core.xml`` emptied. It held a personal account handle. The element stays;
  the creator field, which names Jones, is untouched.

Every other member of each zip is written back unchanged, and every cell, formula and
cached value is untouched. Both removals were Jones's decisions (2026-10-07).

The workbooks are not re-saved through a spreadsheet library. That would rewrite every
member, so the committed file could no longer be shown to be the original.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "notebooks" / "fall-2025"

# sha256 of the originals, as they sat on the shared drive and in searlabtransfer.
ORIGINALS = {
    "EV_Graphs_Updated_Finalist.ipynb":
        "6fbee8c954079bd3699b90880901938228b64913495d86eeacad58d4415cac71",
    "Calculations Check_final.xlsx":
        "3b65a1a460ca653bb45d52b7a03638e232ea891ecbbecde8fd69144e937077ef",
    "Calculations Check_final - Copy.xlsx":
        "7bd095d9ad37009ff97a4157478767e06f2c6b1afdbe8983d2317f3828d69e6d",
}

WORKBOOK_XML = "xl/workbook.xml"
CORE_XML = "docProps/core.xml"

# The whole removed span must be exactly this shape: the wrapper, one absPath, nothing
# else. If Excel ever put anything beside absPath in the wrapper, this refuses rather
# than deleting it.
_ABSPATH_SPAN = re.compile(
    rb'<mc:AlternateContent xmlns:mc="[^"]+">'
    rb'<mc:Choice Requires="x15">'
    rb'<x15ac:absPath url="[^"]*" xmlns:x15ac="[^"]+"/>'
    rb"</mc:Choice></mc:AlternateContent>"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strip_abspath(xml: bytes) -> tuple[bytes, int, int]:
    """Return (stripped xml, start, end) of the single removed span."""
    spans = list(_ABSPATH_SPAN.finditer(xml))
    assert len(spans) == 1, f"expected exactly one absPath wrapper, found {len(spans)}"
    assert xml.count(b"absPath") == 1, "absPath appears outside the expected wrapper"
    start, end = spans[0].span()
    out = xml[:start] + xml[end:]
    assert b"absPath" not in out
    return out, start, end


_LAST_MODIFIED_BY = re.compile(rb"<cp:lastModifiedBy>([^<]*)</cp:lastModifiedBy>")


def empty_last_modified_by(xml: bytes) -> tuple[bytes, int, int]:
    """Return (xml with the element's text removed, start, end) of the removed text."""
    found = list(_LAST_MODIFIED_BY.finditer(xml))
    assert len(found) == 1, f"expected one lastModifiedBy, found {len(found)}"
    start, end = found[0].span(1)
    assert end > start, "lastModifiedBy is already empty"
    return xml[:start] + xml[end:], start, end


# Which spans each workbook loses, by member. Every edit removes one contiguous span.
EDITS = {
    "Calculations Check_final.xlsx": {
        WORKBOOK_XML: (strip_abspath, "<mc:AlternateContent> wrapping one <x15ac:absPath>"),
    },
    "Calculations Check_final - Copy.xlsx": {
        WORKBOOK_XML: (strip_abspath, "<mc:AlternateContent> wrapping one <x15ac:absPath>"),
        CORE_XML: (empty_last_modified_by, "the text of <cp:lastModifiedBy>"),
    },
}


def import_workbook(src: Path, dst: Path, edits: dict) -> dict:
    record: dict = {"members": {}, "edits": {}}
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            original = zin.read(info.filename)
            record["members"][info.filename] = sha256(original)
            data = original
            if info.filename in edits:
                edit, what = edits[info.filename]
                data, start, end = edit(original)
                # A reader without the original can still check that the committed
                # member is the original with one contiguous span removed at this
                # offset: the parts either side are hashed separately.
                record["edits"][info.filename] = {
                    "removed_bytes": [start, end],
                    "sha256_before_span": sha256(original[:start]),
                    "sha256_after_span": sha256(original[end:]),
                    "removed": what,
                }
            # Keep the member's own metadata (order, timestamp, compression method).
            zout.writestr(info, data, compress_type=info.compress_type)
    assert set(record["edits"]) == set(edits), "an expected edit did not happen"
    return record


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    src_dir = Path(argv[1])
    DEST.mkdir(parents=True, exist_ok=True)

    provenance: dict = {
        "imported": "2026-10-07",
        "source": "SEAR Labs shared drive, EV Analysis/Fall 2025/Code and EV Analysis/Data",
        "also_at": "searlabtransfer/EV-Analysis@042738c2bdb2383ba9d36055f5fd342aab61f4a4"
                   " Fall_2025/ (organisation since deleted)",
        "files": {},
    }
    for name, expected in ORIGINALS.items():
        src = src_dir / name
        original = src.read_bytes()
        got = sha256(original)
        assert got == expected, f"{name}: sha256 {got} is not the recorded original"
        dst = DEST / name
        entry: dict = {"original_sha256": expected}
        if name.endswith(".xlsx"):
            entry.update(import_workbook(src, dst, EDITS[name]))
            entry["change"] = "; ".join(f"{m}: {w} removed" for m, (_, w) in EDITS[name].items())
        else:
            shutil.copyfile(src, dst)
            entry["change"] = "none; byte-identical"
        entry["committed_sha256"] = sha256(dst.read_bytes())
        provenance["files"][name] = entry
        print(f"{name}: {entry['change']}")

    out = DEST / "PROVENANCE.json"
    out.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
