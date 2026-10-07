# Test fixtures: what the paper printed and plotted

- `article/`: the article's Tables 1–6, as printed. See `article/README.md`.
- `notebook_figures.csv`: every bar and dot that the published version of Figures 2,
  3 and 5–13 draws, recorded on 2026-10-07 by `scripts/capture_notebook_figures.py`.
  That script ran a temporary copy of the frozen `notebooks/fall-2025/` notebook on a
  fresh kernel (pandas 2.3.3, numpy 2.5.3, matplotlib 3.11.2, openpyxl 3.1.5,
  Python 3.13), with only its three Colab `/content/` paths made relative.
  `tests/test_figures_reproduce.py` checks the package against it.

Both are records of a published result, not outputs of this package. Do not
regenerate them to make a test pass.
