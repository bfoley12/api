from __future__ import annotations

from typing import Any

import httpx

import mp_api.client.contribs.pagination as pagination
from mp_api.client.contribs import helpers
from mp_api.client.contribs._logger import MPCC_LOGGER
from mp_api.client.contribs.helpers import NonEmptyList
from mp_api.client.contribs.models.contributions import (
    Contribution,
    ContributionSubmission,
    ContributionUserSubmission,
)
from mp_api.client.contribs.resources.base import (
    AsyncBaseProtocol,
    AsyncBaseResource,
    BaseProtocol,
    BaseResource,
)
from mp_api.client.contribs.resources.mpc import format_output
from mp_api.client.contribs.resources.shared import UpsertResponse
from mp_api.client.contribs.settings import MPCC_SETTINGS
from mp_api.client.core.exceptions import MPContribsClientError


class ContributionsProtocol(BaseProtocol):
    def get_by_id(self, id: str, fields: list[str] | None) -> Contribution: ...
    def create(
        self,
        contributions: NonEmptyList[ContributionSubmission | dict[str, Any]],
        allow_duplicates: bool = False,
    ) -> list[str]: ...
    def query(
        self,
        query: dict | None = None,
        fields: list | None = None,
        sort: str | None = None,
        _timeout: int = -1,
    ) -> list[Contribution] | pagination.Paginator: ...
    def update(
        self,
        data: ContributionSubmission | dict[str, Any],
        query: dict[str, Any] | None = None,
        _timeout: int = -1,
    ) -> int: ...
    def upsert(
        self, data: NonEmptyList[ContributionSubmission], allow_duplicates: bool = False
    ) -> UpsertResponse: ...
    def remove(self, query: dict[str, Any], _timeout: int = -1) -> int: ...
    def _get_contrib_identifier_payloads(
        self,
        query: dict[str, Any] | None = None,
        include: list[str] | None = None,
        data_id_fields: dict[str, str] | None = None,
        _timeout: int = -1,
    ) -> tuple[list[Contribution], set[str], dict[str, str]]: ...
    def _validate_contributions(
        self,
        contributions: NonEmptyList[dict[str, Any]],
        *,
        project_name: str | None = None,
    ) -> list[ContributionUserSubmission]: ...


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

    @helpers.timeit
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

    def create(
        self,
        contributions: NonEmptyList[ContributionSubmission | dict[str, Any]],
        allow_duplicates=False,
    ) -> list[str]:
        # If given a dict, validate and create ContributionSubmission models
        parsed: list[ContributionSubmission] = [
            c
            if isinstance(c, ContributionSubmission)
            else ContributionSubmission.model_validate(c)
            for c in contributions
        ]

        new_contrib_ids: list[str] = []
        to_submit: list[dict[str, Any]] = []
        # Create each contribution if not duplicate (or if duplicates allowed)
        for contrib in parsed:
            # Search for duplicate contributions
            # Brendan TODO: This check should be handled server-side
            existing_contrib = self.query(query=contrib.id_fields)
            if (not existing_contrib) or allow_duplicates:
                to_submit.append(contrib.model_dump(mode="json"))
        # Bulk post
        res = self.post(json=to_submit)
        new_contrib_ids.append(res["data"]["id"])

        return new_contrib_ids

    def _validate_contributions(
        self,
        contributions: NonEmptyList[dict[str, Any]],
        *,
        project_name: str | None = None,
    ) -> list[ContributionUserSubmission]:
        required_data_keys = {"data"} | set(MPCC_SETTINGS.COMPONENTS)
        for idx, c in enumerate(contributions):
            has_keys = required_data_keys & c.keys()
            if "attachment" in c:
                MPCC_LOGGER.warning(
                    f"attachments are deprecated. Dropping attachments from contribution #{idx}"
                )
                _ = c.pop("attachment")
            if not has_keys:
                raise MPContribsClientError(
                    f"Nothing to submit for contribution #{idx}!"
                )
            elif not all(c[k] for k in has_keys):
                for k in has_keys:
                    if not c[k]:
                        raise MPContribsClientError(
                            f"Empty `{k}` for contribution #{idx}!"
                        )
            if (project_name and "project" not in c) and "identifier" in c:
                contributions[idx]["project"] = project_name
            elif not ("id" in c or ("project" in c and "identifier" in c)):
                raise MPContribsClientError(
                    f"Provide `project` & `identifier`, or `id` for contribution #{idx}!"
                )
        return [
            ContributionUserSubmission.model_validate(contrib)
            for contrib in contributions
        ]

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
        _timeout: int = -1,
    ) -> list[Contribution]:
        """Query contributions.

        See `client.available_query_params()` for keyword arguments used in query.

        Args:
            query (dict): optional query to select contributions
            fields (list): list of fields to include in response
            sort (str): field to sort by; prepend +/- for asc/desc order
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)

        Returns:
            List of contributions
        """
        # Brendan TODO: Should pagination be optional?
        query = query or {}
        if not fields:
            fields = ["_all"]
        query["_fields"] = fields
        if sort:
            query["_sort"] = sort
        # Brendan TODO: On backend-side: we need to be able to handle orphaned refs
        # - This came about by having a contrib with 8 table references, but only creating 2 of the tables
        #     and notebooks not being present
        # - leads to IndexError: list index out of range from REST API (Flask)
        # - Might not happen naturally, but we should be defensive
        contribs = self.get(
            params=query,
            timeout=_timeout,
        )
        return [Contribution.model_validate(c) for c in contribs["data"]]

    @helpers.timeit
    def update(
        self,
        data: ContributionSubmission | dict[str, Any],
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
        if not data:
            raise MPContribsClientError("Nothing to update.")
        query = query or {}
        # Validate identifiying fields: pk (single-contrib update: contributions/{pk}), id (multi-contrib update), or project & identifier (multi-contrib update w/o id)
        pk_present = helpers.find_field_params(field="pk", params=query)
        if not (
            pk_present
            or helpers.find_field_params(field="id", params=query)
            or (
                helpers.find_field_params("project", query)
                and helpers.find_field_params("identifier", query)
            )
        ):
            raise MPContribsClientError(
                f"No identifying fields (pk, id*, or project* & identifier*) provided in query: {query}"
            )

        if isinstance(data, ContributionSubmission):
            data = data.model_dump(mode="json")
        # If updating by single pk, get path (contributions/{pk})
        path = query.pop("pk", "")
        res = self.put(path=path, params=query, json=data)
        num_updated = res["total_count"]

        return num_updated

    def upsert(
        self, data: NonEmptyList[ContributionSubmission], allow_duplicates=False
    ) -> UpsertResponse:
        create_subs = []
        update_subs = []
        update_query: list[dict[str, Any]] = []

        # If we allow duplicates, we are always POSTing new documents
        if allow_duplicates:
            create_subs = data
        # Otherwise, we call PUT and have the server decide
        else:
            # for each contribution, decide whether it is an update or create based on identifier (pk or project & identifier) presence
            for submission in data:
                # See if submission exists (update)
                if existing_id := self._check_exists(submission):
                    update_query.append({"id": existing_id})
                    submission.id = existing_id
                    update_subs.append(submission)
                # Otherwise, it's a create
                else:
                    create_subs.append(submission)
        # Run all updates
        num_updated = 0
        for update_data in zip(update_subs, update_query, strict=True):
            num_updated += self.update(update_data[0], update_data[1])

        # Create new contributions
        new_contrib_ids = self.create(create_subs)

        resp = UpsertResponse(new_ids=new_contrib_ids, num_updated=num_updated)
        return resp

    def _check_exists(self, data: ContributionSubmission) -> str:
        params: dict[str, Any] = {"_fields": ["id"]}
        if data.id:
            params |= {"id": data.id}
        elif data.project and data.identifier:
            params |= {"project": data.project, "identifier": data.identifier}
        resp = self.get(params=params)
        resp_data = resp["data"]
        if not resp_data:
            return ""
        else:
            return resp_data[0]["id"]


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
