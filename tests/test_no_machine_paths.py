"""No committed file carries an absolute path from the machine that wrote it.

Taken from sear-labs/sav-osemosys-trd-2019 with the guard it runs. This repository's
CLAUDE.md named a co-author's home folder until 2026-10-07, and both imported Fall 2025
workbooks recorded the folder they were last saved in (see
scripts/import_fall2025_evidence.py). The guard is watched to fail on each of those in
the pull request that added it.
"""
import importlib.util
import io
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "check_no_machine_paths.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("check_no_machine_paths", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_guard_script_exists():
    assert GUARD.exists(), f"{GUARD.name} is missing - the sweep is the whole protection"


def test_no_committed_file_carries_a_machine_path():
    result = subprocess.run([sys.executable, str(GUARD)], cwd=ROOT,
                            capture_output=True, text=True)
    print(result.stdout, result.stderr)
    assert result.returncode == 0, (
        "a committed file carries an absolute machine path:\n"
        f"{result.stdout}{result.stderr}\n"
        "Fix it where the string is produced, not by normalising the artifact - "
        "a normaliser hides it from every reader who is not diffing bytes."
    )


def test_the_guard_reads_inside_a_workbook():
    """A path that exists only inside a compressed zip member must still be found.

    The real case (Excel's absPath in xl/workbook.xml) cannot be committed as a
    canary, which is the point of the guard, so a workbook-shaped zip is built here.
    """
    guard = _load_guard()
    leak = ("F:" + chr(92) + "Student Drive" + chr(92) + "EV Analysis" + chr(92)).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", b'<x15ac:absPath url="' + leak + b'"/>' * 50)
    raw = buf.getvalue()
    assert leak not in raw, "the canary must be invisible to a scan of compressed bytes"

    found = [
        label for label, blob in guard._blobs("canary.xlsx", raw)
        for pattern in guard._PATTERNS.values() if pattern.search(blob)
    ]
    assert found == ["canary.xlsx!xl/workbook.xml"], found
