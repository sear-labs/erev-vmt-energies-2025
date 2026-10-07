# The article's printed tables, as fixtures

Tables 1–6 of Patil, Kumbhar & Jones, *Energies* **2025**, 18, 6448
(<https://doi.org/10.3390/en18246448>), taken from the HTML tables on mdpi.com on
2026-10-07. Tables 5 and 6 were serialised by script from the page's own `<table>`
elements; the others were copied from the same extraction. The article is CC BY 4.0.

They hold **what was printed, as printed**: `$ 57.47`, `0.0%`, `N/A` and `$-` are kept,
and the tests parse them. Do not correct a value here to make a test pass. A printed
number that the model does not reproduce is a finding, and it goes in the README under
"What reproduces, and what doesn't".

Two changes from the page:

- Bin labels use an ASCII hyphen (`0-1`), not the page's en-dash, because the label is
  a join key (see CLAUDE.md).
- Table 2's month names are written as numbers 1–12.
