from __future__ import annotations

from pydantic import BaseModel

from mp_api.client.contribs.models.base import ContributionsSupplemental


class Lattice(BaseModel):
    pass


class Sites(BaseModel):
    pass


# Some things in Emmet-core that could assist in translating the pymatgen string to BaseModel
# In Mongo it is a single long string, but we could try to parse it into something typed
# It looks like it has some fields, then a table for n_atom_site_* with the subsequent lines being tab/space delimited rows
class Cif(BaseModel):
    pass


class ContributionsStructures(ContributionsSupplemental):
    lattice: Lattice
    sites: Sites
    charge: float | None
    cif: Cif
