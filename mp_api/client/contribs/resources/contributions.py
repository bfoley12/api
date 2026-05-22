from __future__ import annotations

from typing import Any

import httpx

import mp_api.client.contribs.pagination as pagination
from mp_api.client.contribs import helpers
from mp_api.client.contribs._logger import MPCC_LOGGER
from mp_api.client.contribs.models.contributions import Contribution
from mp_api.client.contribs.resources.base import (
    AsyncBaseProtocol,
    AsyncBaseResource,
    BaseProtocol,
    BaseResource,
)
from mp_api.client.contribs.resources.mpc import format_output
from mp_api.client.contribs.settings import MPCC_SETTINGS
from mp_api.client.core.exceptions import MPContribsClientError


class ContributionsProtocol(BaseProtocol):
    def get_by_id(self, id: str, fields: list[str] | None) -> Contribution: ...
    def create(self): ...
    def query(
        self,
        query: dict | None = None,
        fields: list | None = None,
        sort: str | None = None,
        paginate: bool = False,
        _timeout: int = -1,
    ) -> list[Contribution] | pagination.Paginator: ...
    def update(
        self, data: dict, query: dict | None = None, _timeout: int = -1
    ) -> int: ...
    def remove(self, query: dict[str, Any], _timeout: int = -1) -> int: ...
    def _get_contrib_identifier_payloads(
        self,
        query: dict[str, Any] | None = None,
        include: list[str] | None = None,
        data_id_fields: dict[str, str] | None = None,
        _timeout: int = -1,
    ) -> tuple[list[Contribution], set[str], dict[str, str]]: ...


class AsyncContributionsProtocol(AsyncBaseProtocol):
    async def get_by_id(self, id: str, fields: list[str] | None) -> Contribution: ...
    async def create(self): ...
    async def query(
        self,
        query: dict | None = None,
        fields: list | None = None,
        sort: str | None = None,
        paginate: bool = False,
        _timeout: int = -1,
    ) -> list[Contribution] | pagination.Paginator: ...
    async def update(
        self, data: dict, query: dict | None = None, _timeout: int = -1
    ) -> int: ...
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


class ContributionsResource(BaseResource, ContributionsProtocol):
    def __init__(
        self,
        http: httpx.Client,
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
    def get_by_id(self, id: str, fields: list[str] | None) -> Contribution:
        if not fields:
            fields = list(Contribution.model_fields.keys())
            fields.remove("needs_build")  # internal field

        params = {"_fields": ",".join(fields)}
        if not id.endswith("/"):
            id = id + "/"
        contrib = self.get(path=id, params=params)

        return Contribution.model_validate(contrib)

    def create(self):
        pass

    def _get_contrib_identifier_payloads(
        self,
        query: dict[str, Any] | None = None,
        include: list[str] | None = None,
        data_id_fields: dict[str, str] | None = None,
        _timeout: int = -1,
    ) -> tuple[list[Contribution], set[str], dict[str, str]]:
        """Get identifying fields for specified contributions and their components.

        Args:
            query (dict[str, Any]): a query to the REST API for contributions
            include (list[str]): the component types to include
            data_id_fields (dict[str, str]): additional fields to consider as identifying from the data field
            _timeout (int): time before returning (-1 for no timeout)

        Returns:
            A tuple of contribution data, the component types searched, and the data)ud
        """
        include = include or []
        components = {x for x in include if x in MPCC_SETTINGS.COMPONENTS}
        if include and not components:
            raise MPContribsClientError(
                f"`include` must be subset of {MPCC_SETTINGS.COMPONENTS}!"
            )

        query = query or {}
        data_id_fields = data_id_fields or {}

        query = helpers.prune_dict(
            payload=query, disallowed_keys=["name", "page", "per_page", "_fields"]
        )
        id_fields = Contribution.id_keys()
        if data_id_fields:
            id_fields.update(f"data.{field}" for field in data_id_fields.values())

        query["_fields"] = list(id_fields | components)
        contributions = self.fetch_all(
            query=query, model=Contribution, timeout=_timeout
        )
        return contributions, components, data_id_fields

    def remove(self, query: dict[str, Any], _timeout: int = -1) -> int:
        return self.delete(params=query)["count"]

    @format_output
    def query(
        self,
        query: dict | None = None,
        fields: list | None = None,
        sort: str | None = None,
        paginate: bool = False,
        _timeout: int = -1,
    ) -> list[Contribution] | pagination.Paginator:
        """Query contributions.

        See `client.available_query_params()` for keyword arguments used in query.

        Args:
            query (dict): optional query to select contributions
            fields (list): list of fields to include in response
            sort (str): field to sort by; prepend +/- for asc/desc order
            paginate (bool): paginate through all results
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)

        Returns:
            List of contributions
        """
        # Brendan TODO: Should pagination be optional?
        query = query or {}
        query["_fields"] = fields
        query["_sort"] = sort
        return self.fetch_all(
            query=query,
            model=Contribution,
            timeout=_timeout,
        )

    def update(
        self,
        data: dict[str, Any],
        query: dict[str, Any] | None = None,
        _timeout: int = -1,
    ) -> int:
        """Apply the same update to all contributions in a project (matching query).

        See `client.available_query_params()` for keyword arguments used in query.

        Args:
            data (dict): update to apply on every matching contribution
            query (dict): optional query to select contributions
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)
        """
        # Brendan TODO: Decide if contributions should recheck so we can have individual validation
        # if not data:
        #     raise MPContribsClientError("Nothing to update.")

        # tic = time.perf_counter()
        # self._is_valid_payload(Contribution, data)

        # if "data" in data:
        #     self._is_serializable_dict(data["data"])

        # query = query or {}

        # if self.project:
        #     if "project" in query and self.project != query["project"]:
        #         raise MPContribsClientError(
        #             f"client initialized with different project {self.project}!"
        #         )
        #     query["project"] = self.project
        # else:
        #     if not query or "project" not in query:
        #         raise MPContribsClientError(
        #             "initialize client with project, or include project in query!"
        #         )

        # name = query["project"]
        # project_ids = self.get_all_ids(query).get(name)
        # cids = list(self._project_contrib_ids(project_ids))

        # if not cids:
        #     raise MPContribsClientError(
        #         f"There aren't any contributions to update for {name}"
        #     )

        # # get current list of data columns to decide if swagger reload is needed
        # resp = self.projects.getProjectByName(pk=name, _fields=["columns"]).result()
        # old_paths = {c["path"] for c in resp["columns"]}
        query = query or {}
        if "id__in" not in query:
            raise MPContribsClientError(f"no id__in provided in query: {query}")
        res = self.fetch_all(
            query=query, model=Contribution, op=helpers.VALID_OPS.UPDATE
        )
        num_updated = len(res)

        return num_updated


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
        responses = await pagination.paginate(
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

    @format_output
    async def query(
        self,
        query: dict | None = None,
        fields: list | None = None,
        sort: str | None = None,
        paginate: bool = False,
        _timeout: int = -1,
    ) -> list[Contribution] | pagination.Paginator:
        """Query contributions.

        See `client.available_query_params()` for keyword arguments used in query.

        Args:
            query (dict): optional query to select contributions
            fields (list): list of fields to include in response
            sort (str): field to sort by; prepend +/- for asc/desc order
            paginate (bool): paginate through all results
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)

        Returns:
            List of contributions
        """
        query = query or {}
        if paginate:
            query["_fields"] = fields
            query["_sort"] = sort
            return pagination.Paginator(
                self.http,
                f"{self.http.base_url}/{self.endpoint_slug}",
                pagination.Page[Contribution],
                params=query,
            )
        return await pagination.paginate(
            client=self.http,
            url=f"{self.http.base_url}/{self.endpoint_slug}",
            item_model=Contribution,
            params=query,
        )

    async def update(
        self,
        data: dict[str, Any],
        query: dict[str, Any] | None = None,
        _timeout: int = -1,
    ) -> int:
        """Apply the same update to all contributions in a project (matching query).

        See `client.available_query_params()` for keyword arguments used in query.

        Args:
            data (dict): update to apply on every matching contribution
            query (dict): optional query to select contributions
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)
        """
        # Brendan TODO: Decide if contributions should recheck so we can have individual validation
        # if not data:
        #     raise MPContribsClientError("Nothing to update.")

        # tic = time.perf_counter()
        # self._is_valid_payload(Contribution, data)

        # if "data" in data:
        #     self._is_serializable_dict(data["data"])

        # query = query or {}

        # if self.project:
        #     if "project" in query and self.project != query["project"]:
        #         raise MPContribsClientError(
        #             f"client initialized with different project {self.project}!"
        #         )
        #     query["project"] = self.project
        # else:
        #     if not query or "project" not in query:
        #         raise MPContribsClientError(
        #             "initialize client with project, or include project in query!"
        #         )

        # name = query["project"]
        # project_ids = self.get_all_ids(query).get(name)
        # cids = list(self._project_contrib_ids(project_ids))

        # if not cids:
        #     raise MPContribsClientError(
        #         f"There aren't any contributions to update for {name}"
        #     )

        # # get current list of data columns to decide if swagger reload is needed
        # resp = self.projects.getProjectByName(pk=name, _fields=["columns"]).result()
        # old_paths = {c["path"] for c in resp["columns"]}
        query = query or {}
        if "id__in" not in query:
            raise MPContribsClientError(f"no id__in provided in query: {query}")
        res = await pagination.paginate(
            client=self.http,
            url=f"{self.http.base_url}/{self.endpoint_slug}",
            item_model=Contribution,
            params=query,
        )
        num_updated = len(res)

        return num_updated
