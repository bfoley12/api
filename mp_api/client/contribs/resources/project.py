from __future__ import annotations

from typing import Any, cast

from mp_api.client.contribs.models.project import ContribsProject
from mp_api.client.contribs.models.response import Response
from mp_api.client.contribs.pagination import paginate
from mp_api.client.contribs.resources.base import BaseResource
from mp_api.client.contribs.resources.mpc import format_output


class ProjectResource(BaseResource):
    @format_output
    async def get_project_by_name(
        self, name: str, fields: list[Any] | None
    ) -> ContribsProject:
        params: dict[str, str | list[str]] = {}
        params["_fields"] = ",".join(fields) if fields is not None else ["_all"]
        res = await self.get(name, params=params)
        return ContribsProject.model_validate(res)

    def search(self, term: str) -> Response:
        return Response.model_validate(await self.get(path="search", term=term))

    @format_output
    def query(
        self,
        # Brendan TODO: define query as a Pydantic model?
        query: dict[str, Any] | None,
        term: str | None = None,
        fields: list[str] | None = None,
        sort: str | None = None,
        timeout: int = -1,
    ) -> list[ContribsProject]:
        query = query or {}
        if "name" in query:
            return [
                self.get_project_by_name(
                    name=cast(str, query.get("name")), fields=fields
                )
            ]

        if term:
            search_results = self.search(term=term)
            query["name__in"] = search_results["data"]
        query["_fields"] = fields
        query["_sort"] = sort

        res = self.get(query=query)

        _total_count, total_pages = res["total_count"], res["total_pages"]

        if total_pages < 2:
            return [ContribsProject.model_validate(res["data"])]

        # Handle pagination
        contribs_list = paginate(
            client=self.http,
            url=f"{self.http.base_url}/{self.endpoint_slug}",
            item_model=ContribsProject,
        )

        return contribs_list
