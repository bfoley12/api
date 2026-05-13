from __future__ import annotations

from typing import Any, cast

import httpx

from mp_api.client.contribs import helpers
from mp_api.client.contribs.models.project import ContribsProject
from mp_api.client.contribs.models.response import Response
from mp_api.client.contribs.pagination import paginate
from mp_api.client.contribs.resources.base import BaseResource
from mp_api.client.contribs.resources.mpc import format_output
from mp_api.client.core.exceptions import MPContribsClientError


class ProjectResource(BaseResource):
    def __init__(
        self,
        name: str | None,
        http: httpx.AsyncClient,
        use_document_model: bool = True,
        endpoint_slug: str = "",
    ) -> None:
        """Constructor for ProjectResource.

        Takes an optional name when top-level client is scoped to a project.
        """
        super().__init__(http=http, use_document_model=use_document_model, endpoint_slug=endpoint_slug)
        self.name=name

    def _get_name(self, name: str | None) -> str:
        """Reports the name of the project, preferring the name given at construciton."""
        name = self.name or name
        if not name:
            raise MPContribsClientError(
                "initialize client with project or set `name` argument!"
            )
        return name

    @format_output
    async def get_project_by_name(
        self, name: str, fields: list[Any] | None
    ) -> ContribsProject:
        params: dict[str, str | list[str]] = {}
        params["_fields"] = ",".join(fields) if fields is not None else ["_all"]
        res = await self.get(name, params=params)
        return ContribsProject.model_validate(res)

    async def search(self, term: str) -> Response:
        """Queries projects/search for documents matching terms.

        Returns an object holding the result and a count of results that matched.
        """
        return Response.model_validate(await self.get(path="search", term=term))

    @format_output
    async def query(
        self,
        # Brendan TODO: define query as a Pydantic model?
        query: dict[str, Any] | None,
        term: str | None = None,
        fields: list[str] | None = None,
        sort: str | None = None,
        _timeout: int = -1,
    ) -> list[ContribsProject]:
        query = query or {}
        # Brendan TODO: Why do we force this if name is given to client? Shouldn't we allow runtime overrides?
        if self.name or "name" in query:
            return [
                await self.get_project_by_name(
                    name=cast(str, query.get("name")), fields=fields
                )
            ]

        if term:
            search_results = await self.search(term=term)
            query["name__in"] = search_results["data"]
        query["_fields"] = fields
        query["_sort"] = sort

        # Handle pagination
        contribs_list = await paginate(
            client=self.http,
            url=f"{self.http.base_url}/{self.endpoint_slug}",
            item_model=ContribsProject,
        )

        return contribs_list

    def scan(self,
        query: dict[str, Any] | None = None,
        _timeout: int = -1,
        op: helpers.VALID_OPS = helpers.VALID_OPS.QUERY
    ) -> tuple[int, int]:
