from __future__ import annotations

from enum import StrEnum
from typing import Any

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


class ContribsProject(ContribsBase):
    """Define schema for MP Contribs Project."""

    name: str | None = None
    title: str | None = None
    authors: str | None = None
    description: str | None = None
    references: list[Reference] | None = None
    stats: Stats = Field(default_factory=Stats)

    columns: list[Column] = []
    long_title: str | None = None
    is_public: bool = False
    is_approved: bool = False
    unique_identifiers: bool = True
    license: License = License.CCA4
    owner: str | None = None
    other: dict[str, Any] | None = None

    @field_validator("other", mode="before")
    def flatten_other(cls, d: dict) -> dict[str, str | None]:
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
