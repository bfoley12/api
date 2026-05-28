from __future__ import annotations

from typing import Any

import httpx

from mp_api.client.contribs import pagination
from mp_api.client.contribs.helpers import NonEmptyList
from mp_api.client.contribs.models.notebook import Notebook
from mp_api.client.contribs.resources.base import BaseProtocol, BaseResource
from mp_api.client.contribs.resources.shared import UpsertResponse


class NotebookProtocol(BaseProtocol):
    def create(
        self,
        contributions: NonEmptyList[Notebook | dict[str, Any]],
        allow_duplicates: bool = False,
    ) -> list[str]: ...
    def query(
        self,
        query: dict | None = None,
        fields: list | None = None,
        sort: str | None = None,
        _timeout: int = -1,
    ) -> list[Notebook] | pagination.Paginator: ...
    def update(
        self,
        data: Notebook | dict[str, Any],
        query: dict[str, Any] | None = None,
        _timeout: int = -1,
    ) -> int: ...
    def upsert(
        self,
        data: NonEmptyList[Notebook | dict[str, Any]],
        allow_duplicates: bool = False,
    ) -> UpsertResponse: ...
    def remove(self, query: dict[str, Any], _timeout: int = -1) -> int: ...


class NotebookResource(BaseResource, NotebookProtocol):
    def __init__(
        self,
        http: httpx.Client,
        use_document_model: bool = True,
        endpoint_slug: str = "notebooks",
    ) -> None:
        """Constructor for NotebookResource."""
        super().__init__(
            http=http,
            use_document_model=use_document_model,
            endpoint_slug=endpoint_slug,
        )

    def create(
        self,
        contributions: NonEmptyList[Notebook | dict[str, Any]],
        allow_duplicates: bool = False,
    ) -> list[str]:
        return []

    def query(
        self,
        query: dict | None = None,
        fields: list | None = None,
        sort: str | None = None,
        _timeout: int = -1,
    ) -> list[Notebook] | pagination.Paginator:
        return []

    def update(
        self,
        data: Notebook | dict[str, Any],
        query: dict[str, Any] | None = None,
        _timeout: int = -1,
    ) -> int:
        return 0

    def upsert(
        self,
        data: NonEmptyList[Notebook | dict[str, Any]],
        allow_duplicates: bool = False,
    ) -> UpsertResponse:
        return UpsertResponse(new_ids=[""])

    def remove(self, query: dict[str, Any], _timeout: int = -1) -> int:
        return 0
