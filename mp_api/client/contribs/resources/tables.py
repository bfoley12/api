from __future__ import annotations

from typing import Any

import httpx
import polars as pl

from mp_api.client.contribs import pagination
from mp_api.client.contribs.helpers import NonEmptyList
from mp_api.client.contribs.models.tables import Table
from mp_api.client.contribs.resources.base import BaseProtocol, BaseResource
from mp_api.client.contribs.resources.shared import UpsertResponse


class TableProtocol(BaseProtocol):
    def create(
        self,
        contributions: NonEmptyList[Table | dict[str, Any]],
        allow_duplicates: bool = False,
    ) -> list[str]: ...
    def query(
        self,
        query: dict | None = None,
        fields: list | None = None,
        sort: str | None = None,
        _timeout: int = -1,
    ) -> list[Table] | pagination.Paginator: ...
    def update(
        self,
        data: Table | dict[str, Any],
        query: dict[str, Any] | None = None,
        _timeout: int = -1,
    ) -> int: ...
    def upsert(
        self, data: NonEmptyList[Table | pl.DataFrame], allow_duplicates: bool = False
    ) -> UpsertResponse: ...
    def remove(self, query: dict[str, Any], _timeout: int = -1) -> int: ...


class TableResource(BaseResource, TableProtocol):
    def __init__(
        self,
        http: httpx.Client,
        use_document_model: bool = True,
        endpoint_slug: str = "tables",
    ) -> None:
        """Constructor for NotebookResource."""
        super().__init__(
            http=http,
            use_document_model=use_document_model,
            endpoint_slug=endpoint_slug,
        )

    def create(
        self,
        contributions: NonEmptyList[Table | dict[str, Any]],
        allow_duplicates: bool = False,
    ) -> list[str]:
        return []

    def query(
        self,
        query: dict | None = None,
        fields: list | None = None,
        sort: str | None = None,
        _timeout: int = -1,
    ) -> list[Table] | pagination.Paginator:
        return []

    def update(
        self,
        data: Table | dict[str, Any],
        query: dict[str, Any] | None = None,
        _timeout: int = -1,
    ) -> int:
        return 0

    def upsert(
        self, data: NonEmptyList[Table | pl.DataFrame], allow_duplicates: bool = False
    ) -> UpsertResponse:
        return UpsertResponse(new_ids=[""])

    def remove(self, query: dict[str, Any], _timeout: int = -1) -> int:
        return 0
