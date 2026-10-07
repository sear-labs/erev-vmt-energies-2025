"""The deposit metadata avoids every Zenodo trap already paid for in this organisation.

Each check below was a silent failure in another sear-labs repository, found after
the fact:

- CITATION.cff's top-level `license` must be ONE SPDX string. CFF 1.2.0 allows a list;
  Zenodo's ingestion does not, and fails after acknowledging the release.
- .zenodo.json's licence id is `mit-license`, not `mit`. The wrong id is acknowledged
  and produces nothing.
- .zenodo.json carries no `version`; the release tag supplies it.
- Every creator is affiliated, Jones carries his ORCID, access is open, and the deposit
  points at the paper it supplements.
- The two files name the same people in the same order, so the software citation and
  the deposit cannot drift apart.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
UTA = "University of Texas at Arlington"
JONES_ORCID = "0000-0003-0559-4699"
PAPER_DOI = "10.3390/en18246448"


def _zenodo():
    return json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))


def _cff():
    return yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))


def test_citation_licence_is_one_spdx_string():
    licence = _cff()["license"]
    assert isinstance(licence, str), f"CITATION.cff license must be one string, got {licence!r}"
    assert licence == "MIT"


def test_zenodo_licence_and_access():
    z = _zenodo()
    assert z["license"] == "mit-license", z["license"]
    assert z["access_right"] == "open"
    assert z["upload_type"] == "software"
    assert "version" not in z, "leave version out of .zenodo.json; the release tag fills it"


def test_zenodo_creators():
    creators = _zenodo()["creators"]
    assert creators, "no creators"
    for c in creators:
        assert c.get("affiliation") == UTA, c
        assert ", " in c["name"], f"'{c['name']}' is not in 'Family, Given' form"
    jones = [c for c in creators if c["name"].startswith("Jones,")]
    assert len(jones) == 1 and jones[0].get("orcid") == JONES_ORCID, jones


def test_zenodo_points_at_the_paper():
    rel = _zenodo()["related_identifiers"]
    assert any(r["identifier"] == PAPER_DOI and r["relation"] == "isSupplementTo"
               and r["scheme"] == "doi" for r in rel), rel
    assert _cff()["preferred-citation"]["doi"] == PAPER_DOI


def test_citation_and_zenodo_name_the_same_people_in_order():
    cff = [a["family-names"] for a in _cff()["authors"]]
    zen = [c["name"].split(",")[0] for c in _zenodo()["creators"]]
    print(f"CITATION.cff: {cff}\n.zenodo.json: {zen}")
    assert cff == zen
