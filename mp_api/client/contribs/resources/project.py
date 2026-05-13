from __future__ import annotations

from typing import Any, cast

import httpx
from pydantic import BaseModel

from mp_api.client.contribs import helpers
from mp_api.client.contribs._logger import MPCC_LOGGER
from mp_api.client.contribs.models.project import ContribsProject
from mp_api.client.contribs.models.reference import Reference
from mp_api.client.contribs.models.response import Response
from mp_api.client.contribs.pagination import paginate
from mp_api.client.contribs.resources.base import VALID_RESOURCES, BaseResource
from mp_api.client.contribs.resources.mpc import format_output
from mp_api.client.core.exceptions import MPContribsClientError
from mp_api.client.core.schemas import _DictLikeAccess


class ProjectResource(BaseResource):
    def __init__(
        self,
        name: str | None,
        http: httpx.AsyncClient,
        use_document_model: bool = True,
        endpoint_slug: str = "projects",
    ) -> None:
        """Constructor for ProjectResource.

        Takes an optional name when top-level client is scoped to a project.
        """
        super().__init__(
            http=http,
            use_document_model=use_document_model,
            endpoint_slug=endpoint_slug,
        )
        self.name = name

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

    async def create(
        self,
        name: str,
        title: str,
        authors: str,
        description: str,
        url: str,
    ) -> None:
        """Create a project.

        Args:
            name (str): unique name matching `^[a-zA-Z0-9_]{3,31}$`
            title (str): unique title with 5-30 characters
            authors (str): comma-separated list of authors
            description (str): brief description (max 2000 characters)
            url (str): URL for primary reference (paper/website/...)
        """
        queries = [{"name": name}, {"title": title}]
        for query in queries:
            if await self.scan(
                query=query, resource=VALID_RESOURCES.PROJECTS, name=self.name
            ):
                raise MPContribsClientError(f"Project with {query} already exists!")

        project = ContribsProject(
            name=name,
            title=title,
            authors=authors,
            description=description,
            references=[Reference(label="REF", url=url)],
        )
        resp = await self.put(url="", project=project.to_draft())
        owner = resp.get("owner")
        if owner:
            MPCC_LOGGER.info(f"Project `{name}` created with owner `{owner}`")
        else:
            raise MPContribsClientError(resp.get("error", resp))

    async def update(self, update: dict[str, Any], name: str | None = None) -> None:
        """Update project info.

        Args:
            update (dict): dictionary containing project info to update
            name (str): name of the project
        """
        if not update:
            MPCC_LOGGER.warning("nothing to update")
            return

        name = self._get_name(name)

        disallowed = ["stats", "columns"]
        update = helpers.prune_dict(update, disallowed)
        if not update:
            return

        fields = list(ContribsProject.model_fields.keys())
        for k in disallowed:
            fields.remove(k)

        fields.append("stats.contributions")
        project = await self.get_project_by_name(name=name, fields=fields)

        # allow name update only if no contributions in project
        if "name" in update and project.stats.contributions > 0:
            MPCC_LOGGER.warning("removing `name` from update - not allowed.")
            update.pop("name")
            MPCC_LOGGER.error(
                "cannot change project name after contributions submitted."
            )

        # Keep payload keys if they are requested and not None/the same as the stored value
        payload = helpers.prune_dict(
            payload=update,
            required_keys=fields,
            reference=cast(_DictLikeAccess, ContribsProject),
        )
        self._is_valid_payload(cast(BaseModel, ContribsProject), payload)
        resp = await self.put(path=f"{name}", project=payload)
        if not resp.get("count", 0):
            raise MPContribsClientError(resp)

    # Named remove to avoid overriding the base.delete method, which is an http request
    async def remove(self, name: str | None = None) -> None:
        """Delete a project.

        Args:
            name (str): name of the project
        """
        name = self._get_name(name)

        # Brendan TODO: Make a 'require_record' policy?
        if not self.scan(query={"name": name}, resource=VALID_RESOURCES.PROJECTS):
            raise MPContribsClientError(f"Project `{name}` doesn't exist!")

        resp = await self.delete(pk=name)
        if resp and "error" in resp:
            raise MPContribsClientError(resp["error"])
