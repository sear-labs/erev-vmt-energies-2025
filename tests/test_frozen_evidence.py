"""The frozen notebooks and workbooks are what produced the paper, and stay that way.

notebooks/README.md says: do not rewrite, re-execute or strip outputs. That was prose
until 2026-10-07, and prose fails silently. This file makes it fail loudly:

- every frozen file must match notebooks/MANIFEST.sha256 (normalisation stated there);
- every file under notebooks/ must be frozen or named as maintained here, so a new
  piece of evidence cannot arrive without being recorded;
- each imported workbook must be provably its original apart from the spans the import
  removed (scripts/import_fall2025_evidence.py), even without the original.

If one of these goes red, decide what happened before touching the manifest. A
frozen file that changed is a defect in the change, not in the test.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"
MANIFEST = NOTEBOOKS / "MANIFEST.sha256"
PROVENANCE = NOTEBOOKS / "fall-2025" / "PROVENANCE.json"

# Files under notebooks/ that are maintained rather than frozen.
MAINTAINED = {"README.md", "MANIFEST.sha256", "verify.ipynb"}


def _normalised(path: Path) -> bytes:
    raw = path.read_bytes()
    return raw if path.suffix == ".xlsx" else raw.replace(b"\r\n", b"\n")


def _entries() -> list[tuple[str, str]]:
    out = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            digest, name = line.split("  ", 1)
            out.append((digest, name))
    return out


def test_manifest_lists_something():
    entries = _entries()
    assert len(entries) >= 4, f"MANIFEST.sha256 lists only {len(entries)} files"


@pytest.mark.parametrize("digest,name", _entries(), ids=[n for _, n in _entries()])
def test_frozen_file_is_unchanged(digest, name):
    path = NOTEBOOKS / name
    assert path.is_file(), f"frozen file {name} is missing"
    actual = hashlib.sha256(_normalised(path)).hexdigest()
    print(f"{name}: recorded {digest[:12]}, on disk {actual[:12]}")
    assert actual == digest, (
        f"{name} has changed since it was frozen. It is evidence of what produced "
        "the published numbers: do not tidy it, re-execute it or strip its outputs. "
        "Put corrections in src/ and record the divergence in the README."
    )


def test_every_file_under_notebooks_is_frozen_or_maintained():
    frozen = {name for _, name in _entries()}
    present = {
        p.relative_to(NOTEBOOKS).as_posix()
        for p in NOTEBOOKS.rglob("*")
        if p.is_file() and ".ipynb_checkpoints" not in p.parts
    }
    print(f"{len(present)} files under notebooks/: {len(frozen)} frozen, "
          f"{len(present & MAINTAINED)} maintained")
    unaccounted = sorted(present - frozen - MAINTAINED)
    assert not unaccounted, (
        "files under notebooks/ that are neither in MANIFEST.sha256 nor maintained: "
        f"{unaccounted}. Evidence is recorded when it arrives, not later."
    )


def _workbooks():
    record = json.loads(PROVENANCE.read_text(encoding="utf-8"))["files"]
    return [(name, entry) for name, entry in record.items() if name.endswith(".xlsx")]


@pytest.mark.parametrize("name,entry", _workbooks(), ids=[n for n, _ in _workbooks()])
def test_workbook_is_its_original_less_the_recorded_spans(name, entry):
    path = NOTEBOOKS / "fall-2025" / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["committed_sha256"]

    with zipfile.ZipFile(path) as z:
        members = {m: z.read(m) for m in z.namelist()}
    assert set(members) == set(entry["members"]), "zip members added or lost"
    edits = entry["edits"]
    assert "xl/workbook.xml" in edits, "every workbook loses its absPath"

    unchanged = [m for m in members if m not in edits]
    for member in unchanged:
        assert hashlib.sha256(members[member]).hexdigest() == entry["members"][member], (
            f"{name}!{member} differs from the original"
        )

    # Each edited member is its original with one span removed. The parts either side
    # were hashed at import, so this is checkable without the original file.
    for member, edit in edits.items():
        start = edit["removed_bytes"][0]
        data = members[member]
        assert hashlib.sha256(data[:start]).hexdigest() == edit["sha256_before_span"], member
        assert hashlib.sha256(data[start:]).hexdigest() == edit["sha256_after_span"], member
    assert b"absPath" not in members["xl/workbook.xml"]
    if "docProps/core.xml" in edits:
        assert b"<cp:lastModifiedBy></cp:lastModifiedBy>" in members["docProps/core.xml"]
    print(f"{name}: {len(unchanged)} members identical to the original; "
          + "; ".join(f"{m} = original minus bytes {e['removed_bytes']}" for m, e in edits.items()))
