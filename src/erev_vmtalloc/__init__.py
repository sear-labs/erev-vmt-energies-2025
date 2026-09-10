"""EREV vehicle-miles-traveled allocation, as published in Energies 2025, 18, 6448.

The maintained implementation of the model in
Patil, H.V., Kumbhar, A.A. & Jones, E.C., Jr. "Contributions of Extended-Range
Electric Vehicles (EREVs) to Electrified Miles, Emissions and Transportation
Cost Reduction." Energies 2025, 18, 6448. https://doi.org/10.3390/en18246448

`notebooks/2025-12-09-as-published.ipynb` is the frozen original that produced
the published numbers. It is evidence, not a maintained copy; corrections go
here and the divergence is recorded in the README.
"""

__version__ = "1.0.0"

__all__ = ["allocation", "config", "metrics", "report", "scenarios", "sources"]
