#!/usr/bin/env python
"""Record what the frozen Fall 2025 notebook actually plots in each published figure.

    python scripts/capture_notebook_figures.py

Copies notebooks/fall-2025/ into a temporary folder, makes the three Colab
``/content/`` paths relative IN THAT COPY, and runs it top to bottom on a fresh kernel
with a hook that records every bar, line and dot each figure draws. Only the last
version of each figure (the published one) is kept, mapped to the series names that
``erev_vmtalloc.costs.figure_data`` uses, and written to
``tests/fixtures/notebook_figures.csv``. tests/test_figures_reproduce.py compares the
package with that file.

The frozen notebook itself is never opened for writing. Needs the dev extras
(nbclient, ipykernel). Not run by CI: it records an archived stage's output once, and
what it records is committed (standard, Part 2, "Archive the producer; commit what it
produced"). Figure 1's numbers are typed into its cell (CO2 to three decimals); they
are recorded too, and the package's are compared with them at that precision.

Figure 4 needs one addition. Its cell reads ``WEEKLY_TRIPS_PER_BIN``, ``bins`` and
``x_opt``, which the notebook never defines, and without them it draws a hardcoded toy
week. So, in the temporary copy only, a cell is inserted before it that defines them
from the recovered rule (config ``paper_scenarios.weekly_profile``; see
``erev_vmtalloc.costs.weekly_trips_per_household``). The figure is then drawn by the
notebook's own simulation code. Those Figure 4 rows record what the notebook draws
from the recovered inputs, which is why tests/test_figures_reproduce.py also checks
them against measurements of the published image.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import nbformat
from nbclient import NotebookClient

from erev_vmtalloc import costs, sources
from erev_vmtalloc.allocation import fit_bin_distances
from erev_vmtalloc.config import load_config

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "notebooks" / "fall-2025"
OUT = ROOT / "tests" / "fixtures" / "notebook_figures.csv"

RANGES = ["25", "50", "75", "100", "125", "150"]
SCENARIOS = ["Worst", "Average", "Best"]
FREQUENCIES = [7, 5, 3, 2]

# The published version of each figure: the last cell under its heading.
PUBLISHED_CELL = {1: 2, 2: 4, 3: 7, 4: 9, 5: 13, 6: 17, 7: 21, 8: 25, 9: 29, 10: 37, 11: 43, 12: 47,
                  13: 51}

HOOK = r'''
import json, matplotlib.pyplot as plt
_CAP = {}
def _grab(tag):
    out = []
    for n in plt.get_fignums():
        for ax in plt.figure(n).axes:
            bars = [{"label": str(c.get_label()), "h": [float(p.get_height()) for p in c.patches]}
                    for c in ax.containers if getattr(c, "patches", None)]
            dots = [[float(y) for _, y in c.get_offsets()] for c in ax.collections
                    if len(c.get_offsets())]
            lines = [[float(v) for v in ln.get_ydata()] for ln in ax.get_lines()
                     if len(ln.get_ydata()) == 7]
            child = [list(map(float, c.get_ylim())) for c in getattr(ax, "child_axes", [])]
            out.append({"bars": bars, "dots": dots, "lines": lines,
                        "ylim": list(map(float, ax.get_ylim())), "child_ylims": child})
    if out:
        _CAP.setdefault(str(tag), []).extend(out)
_show0 = plt.show
def _show(*a, **k):
    _grab(_CELL)
    return _show0(*a, **k)
plt.show = _show
'''


def figure4_inputs() -> str:
    """Source for a cell defining the variables Figure 4's cell looks for."""
    config = load_config(ROOT / "config" / "base.yaml")
    raw = ROOT / "data" / "raw"
    fitted = fit_bin_distances(sources.load_bts_trips(raw, config.year),
                               sources.load_fhwa_vmt(raw, config.year), config["bin_bounds"],
                               normalize_to_fhwa=config.normalize_to_fhwa)
    trips = costs.weekly_trips_per_household(fitted, config)
    return ("import numpy as np\n"
            f"bins = {list(fitted.bins)!r}\n"
            f"x_opt = np.array({[float(v) for v in fitted.mean_distance]!r})\n"
            f"WEEKLY_TRIPS_PER_BIN = {dict(zip(fitted.bins, map(float, trips), strict=True))!r}\n")


def run_instrumented(workdir: Path) -> dict:
    nb = nbformat.read(workdir / "EV_Graphs_Updated_Finalist.ipynb", as_version=4)
    cells = [nbformat.v4.new_code_cell(HOOK)]
    for i, cell in enumerate(nb.cells):
        if i == PUBLISHED_CELL[4]:
            cells.append(nbformat.v4.new_code_cell(figure4_inputs()))
        if cell.cell_type == "code":
            cell.source = (f"_CELL = {i}\n" + cell.source.replace("/content/", "")
                           + "\n_grab(_CELL); plt.close('all')\n")
        cells.append(cell)
    cells.append(nbformat.v4.new_code_cell("json.dump(_CAP, open('captured.json', 'w'))"))
    nb.cells = cells
    NotebookClient(nb, timeout=600, allow_errors=False,
                   resources={"metadata": {"path": str(workdir)}}).execute()
    return json.loads((workdir / "captured.json").read_text())


def _rows(fig, series, xs, ys):
    assert len(xs) == len(ys), (fig, series, len(xs), len(ys))
    return [(fig, series, str(x), float(y)) for x, y in zip(xs, ys, strict=True)]


def map_published(cap: dict) -> list[tuple]:
    """Name every captured series the way costs.figure_data does."""
    rows = []

    def axes(fig):
        return cap[str(PUBLISHED_CELL[fig])]

    for fig, name in ((2, "installed battery (TWh)"), (3, "battery capital cost ($T)")):
        for bar in axes(fig)[0]["bars"]:
            rows += _rows(fig, f"{bar['label']} {name}", RANGES, bar["h"])

    labels = costs.FIGURE1_ORDER
    ax1 = axes(1)
    rows += _rows(1, "CO2 (Bt)", labels, ax1[0]["bars"][0]["h"])
    # The cell draws the VMT dots on the CO2 axis, scaled by (max CO2) / (max VMT), and
    # labels them with a secondary axis. Undo the scaling with the two axes' own
    # limits: the secondary axis's top is the CO2 axis's top in VMT units.
    host = next(a for a in ax1 if a["dots"])
    (sec_top,) = {c[1] for c in host["child_ylims"]}
    to_vmt = sec_top / host["ylim"][1]
    rows += _rows(1, "VMT (T)", labels, [v * to_vmt for v in host["dots"][0]])

    # Figure 4: the cell draws two 4x4 grids; the second is the published one.
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    grid = axes(4)[-16:]
    for i, cpw in enumerate(FREQUENCIES):
        for j, r in enumerate([50, 75, 100, 150]):
            ax = grid[i * 4 + j]
            assert len(ax["bars"]) == 2 and len(ax["lines"]) == 1, (cpw, r, ax)
            rows += _rows(4, f"{cpw}/week R={r} EV miles", days, ax["bars"][0]["h"])
            rows += _rows(4, f"{cpw}/week R={r} gas miles", days, ax["bars"][1]["h"])
            rows += _rows(4, f"{cpw}/week R={r} start-of-day range", days, ax["lines"][0])

    bars = axes(5)[0]["bars"]
    for k, cpw in enumerate(FREQUENCIES):
        rows += _rows(5, f"{cpw}/week electric VMT (T)", RANGES, bars[2 * k]["h"])
        rows += _rows(5, f"{cpw}/week gas VMT (T)", RANGES, bars[2 * k + 1]["h"])
    rows += _rows(5, "dots: electric VMT if charged before each trip (T)", RANGES,
                  axes(5)[1]["dots"][0])

    bars = axes(6)[0]["bars"]
    for k, s in enumerate(SCENARIOS):
        xs = ["ICE"] + RANGES + ["EV"]
        rows += _rows(6, f"{s} gas CO2 (Bt)", xs, bars[2 * k]["h"])
        rows += _rows(6, f"{s} grid CO2 (Bt)", xs, bars[2 * k + 1]["h"])

    # Figure 7: one bar pair per position - ICE, then each range at 7/5/3/2, then EV.
    pairs = [(axes(7)[0]["bars"][i]["h"][0], axes(7)[0]["bars"][i + 1]["h"][0])
             for i in range(0, len(axes(7)[0]["bars"]), 2)]
    assert len(pairs) == 2 + len(RANGES) * len(FREQUENCIES), len(pairs)
    rows += _rows(7, "ICE gas CO2 (Bt)", ["ICE"], [pairs[0][0]])
    for j, r in enumerate(RANGES):
        for k, cpw in enumerate(FREQUENCIES):
            gas, grid = pairs[1 + j * len(FREQUENCIES) + k]
            rows += _rows(7, f"{cpw}/week gas CO2 (Bt)", [r], [gas])
            rows += _rows(7, f"{cpw}/week grid CO2 (Bt)", [r], [grid])
    rows += _rows(7, "EV grid CO2 (Bt)", ["EV"], [pairs[-1][1]])

    for fig, bar_name, dot_name, keys in (
        (8, "CAPEX per EV mile ($)", "electric VMT (T)", SCENARIOS),
        (9, "CAPEX per EV mile ($)", "electric VMT (T)", [f"{c}/week" for c in FREQUENCIES]),
        (10, "CAPEX per ton CO2 saved ($)", "CO2 saved (Mt)", SCENARIOS),
        (11, "CAPEX per ton CO2 saved ($)", "CO2 saved (Mt)", [f"{c}/week" for c in FREQUENCIES]),
    ):
        bars, dots = axes(fig)[0]["bars"], axes(fig)[1]["dots"]
        assert len(bars) == len(dots) == len(keys), (fig, len(bars), len(dots))
        for key, bar, dot in zip(keys, bars, dots, strict=True):
            rows += _rows(fig, f"{key} {bar_name}", RANGES, bar["h"])
            rows += _rows(fig, f"{key} {dot_name}", RANGES, dot)

    for fig, keys in ((12, SCENARIOS), (13, [f"{c}/week" for c in FREQUENCIES])):
        bars = axes(fig)[0]["bars"]
        for k, key in enumerate(keys):
            rows += _rows(fig, f"{key} gas OPEX ($B)", RANGES, bars[2 * k]["h"])
            rows += _rows(fig, f"{key} electricity OPEX ($B)", RANGES, bars[2 * k + 1]["h"])
    return rows


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for f in SOURCE.iterdir():
            if f.suffix in (".ipynb", ".xlsx"):
                shutil.copyfile(f, work / f.name)
        cap = run_instrumented(work)
    rows = map_published(cap)
    lines = ["figure,series,x,y"] + [f'{f},"{s}",{x},{y!r}' for f, s, x, y in rows]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} plotted values from {len(PUBLISHED_CELL)} figures to "
          f"{OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
