from __future__ import annotations

from enum import StrEnum
from typing import Any, TypedDict

from pydantic import Field, field_serializer, field_validator

from mp_api.client.contribs.models.base import ContribsBase
from mp_api.client.contribs.models.column import Column
from mp_api.client.contribs.models.reference import Reference
from mp_api.client.contribs.models.stats import Stats
from mp_api.client.contribs.utils import flatten_dict, unflatten_dict


# Brendan TODO: Might be overkill, but if we think this could expand or be used in UI, might be useful
class License(StrEnum):
    CCA4 = "CCA4"
    CCPD = "CCPD"


class ContribsProjectFields(TypedDict):
    """Define fields for MP Contribs Project.

    This gives IDE hints when unpacked in a method's kwargs in Python >=3.12.

    Examples:
        from typing import Unpack
        def create_project(self, **kwargs: Unpack[ContribsProjectFields]) -> ...
    """

    name: str
    title: str
    authors: str
    # Project is required by the API server, but sets whatever it is to the email that posted it
    # - api should either not require it or make it optional
    owner: str
    description: str
    references: list[Reference]

    columns: list[Column]
    long_title: str
    is_public: bool
    is_approved: bool
    unique_identifiers: bool
    license: License
    other: dict[str, Any]


class ContribsProject(ContribsBase):
    """Define schema for MP Contribs Project."""

    name: str | None = Field(default=None, max_length=30, min_length=3)
    title: str | None = Field(default=None, max_length=30, min_length=3)
    owner: str | None = None
    references: list[Reference] = []

    authors: str = ""
    description: str = ""
    stats: Stats = Field(default_factory=Stats)

    long_title: str | None = None
    columns: list[Column] = []
    is_public: bool = False
    is_approved: bool = False
    unique_identifiers: bool = True
    license: License = License.CCA4
    other: dict[str, Any] = {}

    @field_validator("other", mode="before")
    def flatten_other(cls, d: dict[str, Any]) -> dict[str, str | None]:
        """Flatten column metadata."""
        if all(isinstance(v, str) for v in d.values()):
            return d
        return flatten_dict(d)

    @field_serializer("other", mode="plain")
    def unflatten_other(self, v: dict[str, str]) -> dict[str, Any]:
        """Unflatten column metadata."""
        return unflatten_dict(v or {})

    def to_draft(self) -> dict[str, Any]:
        """Strip out fields that cannot be used in creating a project.

        The API forbids including `is_public` and `is_approved` when
        submitting a project, even if these fields are False.
        """
        return {
            k: v
            for k, v in self.model_dump().items()
            if k not in {"is_approved", "is_public"}
        }
