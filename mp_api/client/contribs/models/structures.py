from __future__ import annotations

import polars as pl
from pydantic import BaseModel, ConfigDict
from pymatgen.core import Element

from mp_api.client.contribs.models.base import ContributionsSupplemental


class SiteProperties(BaseModel):
    magmom: float


class Species(BaseModel):
    element: Element
    occu: int


class Lattice(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    matrix: pl.DataFrame
    pbc: list[bool]
    a: float
    b: float
    c: float
    alpha: float
    beta: float
    gamma: float
    volume: float


class Site(BaseModel):
    species: list[Species]
    abc: list[float]
    properties: SiteProperties
    label: str
    xyz: list[float]


# Some things in Emmet-core that could assist in translating the pymatgen string to BaseModel
# In Mongo it is a single long string, but we could try to parse it into something typed
# It looks like it has some fields, then a table for n_atom_site_* with the subsequent lines being tab/space delimited rows
class Cif(BaseModel):
    pass


class ContributionsStructures(ContributionsSupplemental):
    lattice: Lattice
    sites: list[Site]
    charge: float | None
    cif: Cif
