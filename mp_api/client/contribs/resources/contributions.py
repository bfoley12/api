from __future__ import annotations

from typing import Any

import httpx

from mp_api.client.contribs import MPCC_SETTINGS, MPContribsClientError, helpers
from mp_api.client.contribs._logger import MPCC_LOGGER
from mp_api.client.contribs.models.contributions import Contribution
from mp_api.client.contribs.pagination import paginate
from mp_api.client.contribs.resources.base import AsyncBaseProtocol, AsyncBaseResource
from mp_api.client.contribs.resources.mpc import format_output


class AsyncContributionsProtocol(AsyncBaseProtocol):
    async def get_by_id(self, id: str, fields: list[str] | None) -> Contribution: ...
    async def create(self): ...
    async def query(self): ...
    async def update(self): ...
    async def remove(
        self, project_ids: list[str], query: dict[str, Any], _timeout: int = -1
    ) -> int: ...
    async def _get_contrib_identifier_payloads(
        self,
        query: dict[str, Any] | None = None,
        include: list[str] | None = None,
        data_id_fields: dict[str, str] | None = None,
        _timeout: int = -1,
    ) -> tuple[list[dict[str, Any]], set[str], dict[str, str]]: ...


class AsyncContributionsResource(AsyncBaseResource, AsyncContributionsProtocol):
    def __init__(
        self,
        http: httpx.AsyncClient,
        use_document_model: bool = True,
        endpoint_slug: str = "contributions",
    ) -> None:
        """Constructor for AsyncContributionsResource."""
        super().__init__(
            http=http,
            use_document_model=use_document_model,
            endpoint_slug=endpoint_slug,
        )

    @format_output
    async def get_by_id(self, id: str, fields: list[str] | None) -> Contribution:
        if not fields:
            fields = list(Contribution.model_fields.keys())
            fields.remove("needs_build")  # internal field

        contrib = await self.get(pk=id, _fields=fields)

        return contrib

    async def create(self):
        pass

    async def query(self):
        pass

    async def update(self):
        pass

    async def _get_contrib_identifier_payloads(
        self,
        query: dict[str, Any] | None = None,
        include: list[str] | None = None,
        data_id_fields: dict[str, str] | None = None,
        _timeout: int = -1,
    ) -> tuple[list[dict[str, Any]], set[str], dict[str, str]]:
        include = include or []
        components = {x for x in include if x in MPCC_SETTINGS.COMPONENTS}
        if include and not components:
            raise MPContribsClientError(
                f"`include` must be subset of {MPCC_SETTINGS.COMPONENTS}!"
            )

        query = query or {}
        data_id_fields = data_id_fields or {}

        query = helpers.prune_dict(
            payload=query, disallowed_keys=["page", "per_page", "_fields"]
        )

        id_fields = Contribution.id_keys()
        if data_id_fields:
            id_fields.update(f"data.{field}" for field in data_id_fields.values())

        query["_fields"] = list(id_fields | components)
        responses = await paginate(
            client=self.http,
            url=self.endpoint_slug,
            item_model=Contribution,
            params=query,
            _timeout=_timeout,
        )

        contributions: list[dict[str, Any]] = []
        for resp in responses:
            data = resp.get("data", [])
            if isinstance(data, list):
                contributions.extend(data)

        return contributions, components, data_id_fields

    async def remove(
        self, project_ids: list[str], query: dict[str, Any], _timeout: int = -1
    ) -> int:
        cids = await self.get(params={"project__in": project_ids})

        if not cids:
            MPCC_LOGGER.info(
                f"There aren't any contributions to delete for {project_ids}"
            )
            return 0
        query["id__in"] = cids

        return (await self.delete(params=query))["count"]
