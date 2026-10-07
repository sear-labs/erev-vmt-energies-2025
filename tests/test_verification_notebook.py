"""notebooks/verify.ipynb runs with no network and no API key, and says what it says.

The notebook claims to need neither. A claim about what something NEEDS cannot be checked
by reading it (standard, Part 6), so this executes it for real, in memory, with:

- every outbound connection refused. The first, injected cell replaces
  socket.socket.connect and proves the block works before anything else runs. The
  kernel's own channel to this process is ZeroMQ, which does not use Python sockets.
- CENSUS_API_KEY removed from the kernel's environment.

The committed notebook is never written to. Its last line, the VERDICT, must match a
fresh run, so a committed result that has gone stale fails here.
"""
from __future__ import annotations

import os
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "verify.ipynb"

BLOCK_NETWORK = '''
import socket
_real_connect = socket.socket.connect
def _refuse(self, address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) else address
    if host in ("127.0.0.1", "::1", "localhost"):
        return _real_connect(self, address, *args, **kwargs)
    raise OSError(f"network blocked by tests/test_verification_notebook.py: {address!r}")
socket.socket.connect = _refuse
# Prove the block fires before trusting a run that "needed no network".
try:
    socket.create_connection(("93.184.215.14", 80), timeout=2)
    raise AssertionError("the network block did not block")
except OSError as exc:
    assert "network blocked" in str(exc), exc
import os
assert "CENSUS_API_KEY" not in os.environ
'''


def _verdict(nb) -> str:
    text = "".join(o.get("text", "") for o in nb.cells[-1].get("outputs", [])
                   if o.get("output_type") == "stream")
    lines = [ln for ln in text.splitlines() if ln.startswith("VERDICT:")]
    assert lines, f"no VERDICT line in the last cell's output: {text!r}"
    return lines[-1]


def test_runs_offline_without_a_key_and_matches_what_is_committed(monkeypatch):
    committed = nbformat.read(NOTEBOOK, as_version=4)
    expected = _verdict(committed)

    nb = nbformat.read(NOTEBOOK, as_version=4)
    nb.cells.insert(0, nbformat.v4.new_code_cell(BLOCK_NETWORK))
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    assert "CENSUS_API_KEY" not in os.environ
    # The kernel is a separate process, so conftest.py's bare-clone fallback does not
    # reach it. Give it the same source tree this suite is testing.
    monkeypatch.setenv("PYTHONPATH",
                       os.pathsep.join(filter(None, [str(ROOT / "src"),
                                                     os.environ.get("PYTHONPATH")])))
    NotebookClient(nb, timeout=300, allow_errors=False,
                   resources={"metadata": {"path": str(NOTEBOOK.parent)}}).execute()

    fresh = _verdict(nb)
    print(f"committed: {expected}\nfresh:     {fresh}")
    assert fresh == expected, "notebooks/verify.ipynb's committed output is stale; re-execute it"
    assert " 0 do not." in fresh


def test_committed_notebook_is_executed():
    """Shipped executed (standard, Part 5): every code cell has run, in order."""
    nb = nbformat.read(NOTEBOOK, as_version=4)
    counts = [c.execution_count for c in nb.cells if c.cell_type == "code"]
    assert counts and all(counts), "a code cell has not been executed"
    assert counts == sorted(counts), f"cells were not run top to bottom: {counts}"
