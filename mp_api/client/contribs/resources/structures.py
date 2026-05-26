from __future__ import annotations

from typing import Any

import httpx

from mp_api.client.contribs import pagination
from mp_api.client.contribs.models.structures import (
    ContributionsStructures,
    StructureSubmission,
)
from mp_api.client.contribs.resources.base import BaseProtocol, BaseResource


class StructureProtocol(BaseProtocol):
    def create(
        self,
        data: list[ContributionsStructures | dict[str, Any]],
        allow_duplicates: bool = False,
    ) -> list[str]: ...
    def query(
        self,
        query: dict | None = None,
        fields: list | None = None,
        sort: str | None = None,
        _timeout: int = -1,
    ) -> list[ContributionsStructures] | pagination.Paginator: ...
    def update(
        self,
        data: StructureSubmission | dict[str, Any],
        query: dict[str, Any] | None = None,
        _timeout: int = -1,
    ) -> int: ...
    def upsert(
        self, data: list[StructureSubmission], allow_duplicates: bool = False
    ) -> dict[str, Any]: ...
    def remove(self, query: dict[str, Any], _timeout: int = -1) -> int: ...


class StructureResource(BaseResource, BaseProtocol):
    def __init__(
        self,
        http: httpx.Client,
        use_document_model: bool = True,
        endpoint_slug: str = "structures",
    ) -> None:
        """Constructor for AsyncContributionsResource."""
        super().__init__(
            http=http,
            use_document_model=use_document_model,
            endpoint_slug=endpoint_slug,
        )

    def upsert(
        self, data: list[StructureSubmission], allow_duplicates: bool = False
    ) -> dict[str, Any]:
        return {}
