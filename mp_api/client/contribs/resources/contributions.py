from __future__ import annotations

from typing import Protocol

import httpx

from mp_api.client.contribs.models.contributions import Contribution
from mp_api.client.contribs.resources.base import AsyncBaseResource
from mp_api.client.contribs.resources.mpc import format_output


class AsyncContributionsProtocol(Protocol):
    async def get_by_id(self, id: str, fields: list[str] | None) -> Contribution: ...
    async def create(self): ...
    async def query(self): ...
    async def update(self): ...
    async def remove(self): ...


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

    async def remove(self):
        pass
