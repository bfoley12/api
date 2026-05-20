from __future__ import annotations

from math import isclose
from typing import Any, cast

import httpx
from pint.errors import DimensionalityError

from mp_api.client.contribs import helpers
from mp_api.client.contribs._logger import MPCC_LOGGER
from mp_api.client.contribs._units import ureg
from mp_api.client.contribs.models.project import ContribsProject
from mp_api.client.contribs.models.reference import Reference
from mp_api.client.contribs.models.response import Response
from mp_api.client.contribs.pagination import paginate
from mp_api.client.contribs.resources.base import (
    VALID_RESOURCES,
    AsyncBaseProtocol,
    AsyncBaseResource,
    BaseProtocol,
    BaseResource,
)
from mp_api.client.contribs.resources.mpc import format_output
from mp_api.client.contribs.settings import MPCC_SETTINGS
from mp_api.client.contribs.utils import flatten_dict, unflatten_dict
from mp_api.client.core.exceptions import MPContribsClientError
from mp_api.client.core.schemas import _DictLikeAccess


class ProjectProtocol(BaseProtocol):
    name: str | None

    def get_project_by_name(
        self, name: str | None, fields: list[Any] | None, **kwargs
    ) -> ContribsProject: ...

    def query(
        self,
        # Brendan TODO: define query as a Pydantic model?
        query: dict[str, Any] | None,
        term: str | None = None,
        fields: list[str] | None = None,
        sort: str | None = None,
        _timeout: int = -1,
    ) -> list[ContribsProject]: ...

    def create(
        self,
        name: str,
        title: str,
        authors: str,
        description: str,
        url: str,
    ) -> None: ...

    def update(
        self, update: dict[str, Any], name: str | None = None
    ) -> ContribsProject: ...

    def remove(self, name: str | None = None) -> None: ...

    def get_unique_identifiers_flags(
        self, query: dict[str, Any] | None = None
    ) -> dict[str, bool]: ...

    def init_columns(
        self, columns: dict | None = None, name: str | None = None
    ) -> ContribsProject: ...

    def validate_query_project(self, query: dict[str, Any]): ...


class AsyncProjectProtocol(AsyncBaseProtocol):
    name: str | None

    async def get_project_by_name(
        self, name: str | None, fields: list[Any] | None, **kwargs
    ) -> ContribsProject: ...

    async def query(
        self,
        # Brendan TODO: define query as a Pydantic model?
        query: dict[str, Any] | None,
        term: str | None = None,
        fields: list[str] | None = None,
        sort: str | None = None,
        _timeout: int = -1,
    ) -> list[ContribsProject]: ...

    async def create(
        self,
        name: str,
        title: str,
        authors: str,
        description: str,
        url: str,
    ) -> None: ...

    async def update(
        self, update: dict[str, Any], name: str | None = None
    ) -> ContribsProject: ...

    async def remove(self, name: str | None = None) -> None: ...

    async def get_unique_identifiers_flags(
        self, query: dict[str, Any] | None = None
    ) -> dict[str, bool]: ...

    async def init_columns(
        self, columns: dict | None = None, name: str | None = None
    ) -> ContribsProject: ...

    def validate_query_project(self, query: dict[str, Any]): ...


class ProjectResource(BaseResource, ProjectProtocol):
    def __init__(
        self,
        name: str | None,
        http: httpx.Client,
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

    # Brendan TODO: Is it more idiomatic to prefer the newly supplied name and set self.name = name?
    def _get_name(self, name: str | None) -> str:
        """Reports the name of the project, preferring the name given at construciton."""
        name = self.name or name
        if not name:
            raise MPContribsClientError(
                "initialize client with project or set `name` argument!"
            )
        if not name.endswith("/"):
            name = name + "/"
        return name

    @format_output
    def get_project_by_name(
        self,
        name: str | None,
        fields: list[Any] | None,
        **kwargs,
    ) -> ContribsProject:
        """Get a project by referencing its name.

        Args:
            name (str): the name of the project to search. If self.name is not None, prefer to use that over the supplied name
            fields (list[str] | None): a list of fields to return. If none are supplied return all fields
            kwargs (dict): allows for pass-through of arguments for retry behavior
        """
        name = self._get_name(name)
        params: dict[str, str | list[str]] = {}
        params["_fields"] = ",".join(fields) if fields else ["_all"]
        res = self.get(name, params=params)
        return ContribsProject.model_validate(res)

    def search(self, term: str) -> Response:
        """Queries projects/search for documents matching terms.

        Returns an object holding the result and a count of results that matched.
        """
        return Response.model_validate(self.get(path="search", term=term))

    @format_output
    def query(
        self,
        # Brendan TODO: define query as a Pydantic model?
        query: dict[str, Any] | None,
        term: str | None = None,
        fields: list[str] | None = None,
        sort: str | None = None,
        _timeout: int = -1,
    ) -> list[ContribsProject]:
        """Query projects by query and/or term (Atlas Search).

        See `client.available_query_params(resource="projects")` for keyword arguments used in
        query. Provide `term` to search for a term across all text fields in the project infos.

        Args:
            query (dict): optional query to select projects
            term (str): optional term to search text fields in projects
            fields (list): list of fields to include in response
            sort (str): field to sort by; prepend +/- for asc/desc order
            _timeout (int): cancel remaining requests if timeout exceeded (in seconds)

        Returns:
            List of projects as validated `ContribsProject`s
                (use_document_model = True) and `dict`s (otherwise).
        """
        query = query or {}
        # Brendan TODO: Why do we force this if name is given to client? Shouldn't we allow runtime overrides?
        if self.name or "name" in query:
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

        # Handle pagination
        project_list = self.fetch_all(
            query=query,
            model=ContribsProject,
            op=helpers.VALID_OPS.QUERY,
            resource=VALID_RESOURCES.PROJECTS,
        )
        return project_list

    def create(
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
            if self.scan(
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
        resp = self.put(url="", project=project.to_draft())
        owner = resp.get("owner")
        if owner:
            MPCC_LOGGER.info(f"Project `{name}` created with owner `{owner}`")
        else:
            raise MPContribsClientError(resp.get("error", resp))

    def update(
        self, update: dict[str, Any], name: str | None = None
    ) -> ContribsProject:
        """Update project info.

        Args:
            update (dict): dictionary containing project info to update
            name (str): name of the project
        """
        if not update:
            MPCC_LOGGER.warning("nothing to update")
            raise MPContribsClientError("No update dict provided")

        name = self._get_name(name)

        disallowed = ["stats", "columns"]
        update = helpers.prune_dict(update, disallowed)
        if not update:
            raise MPContribsClientError(
                f"no valid keys given in udpate dict. Must not only contain {disallowed}"
            )

        fields = list(ContribsProject.model_fields.keys())
        for k in disallowed:
            fields.remove(k)

        fields.append("stats.contributions")
        project = self.get_project_by_name(name=name, fields=fields)

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
        return_value = self._is_valid_payload(ContribsProject, payload)
        resp = self.put(path=f"{name}", project=payload)
        if not resp.get("count", 0):
            raise MPContribsClientError(resp)
        return return_value

    # Named remove to avoid overriding the base.delete method, which is an http request
    def remove(self, name: str | None = None) -> None:
        """Delete a project.

        Args:
            name (str): name of the project
        """
        name = self._get_name(name)

        # Brendan TODO: Make a 'require_record' policy?
        if not self.scan(query={"name": name}, resource=VALID_RESOURCES.PROJECTS):
            raise MPContribsClientError(f"Project `{name}` doesn't exist!")

        resp = self.delete(pk=name)
        if resp and "error" in resp:
            raise MPContribsClientError(resp["error"])

    def get_unique_identifiers_flags(
        self, query: dict[str, Any] | None = None
    ) -> dict[str, bool]:
        """Retrieve values for `unique_identifiers` flags.

        See `client.available_query_params(resource="projects")` for available query parameters.

        Args:
            query (dict): query to select projects

        Returns:
            dict of str to bool, ex.:
            {"<project-name>": True|False, ...}
        """
        results = self.query(query=query, fields=["name", "unique_identifiers"])
        return {p["name"]: p["unique_identifiers"] for p in results}

    def init_columns(
        self, columns: dict | None = None, name: str | None = None
    ) -> ContribsProject:
        """Initialize columns for a project to set their order and desired units.

        The `columns` field of a project tracks the minima and maxima of each `data` field
        in its contributions. If columns are not initialized before submission using this
        function, `submit_contributions` will respect the order of columns as they are
        submitted and will try to auto-determine suitable units.

        `init_columns` can be used at any point to reset the order of columns. Omitting
        the `columns` argument will re-initialize columns based on the `data` fields of
        all submitted contributions.

        The `columns` argument is a dictionary which maps the data field names to its
        units. Use `None` to indicate that a field is not a quantity (plain string). The
        unit for a dimensionless quantity is an empty string (""). Percent (`%`) and
        permille (`%%`) are considered units. Nested fields are indicated using a dot
        (".") in the data field name.

        Example:
        >>> client.init_columns({"a": None, "b.c": "eV", "b.d": "mm", "e": ""})

        This example will result in column headers on the project landing page of the form


        |      |      data       |      |
        | data |        b        | data |
        |   a  | c [eV] | d [mm] | e [] |


        Args:
            columns (dict): dictionary mapping data column to its unit
            name (str or None) : optional name of the project to use,
                defaults to `self.project`.

        Returns:
            dict containing metadata about the column updates
        """
        name = self._get_name(name)

        columns = flatten_dict(columns or {})

        if len(columns) > MPCC_SETTINGS.MAX_COLUMNS:
            raise MPContribsClientError(
                f"Number of columns larger than {MPCC_SETTINGS.MAX_COLUMNS}!"
            )

        if not all(isinstance(v, str) for v in columns.values() if v is not None):
            raise MPContribsClientError(
                "All values in `columns` need to be None or of type str!"
            )

        new_columns = []

        if columns:
            # check columns input
            scanned_columns = set()

            # Gets valid column names into scanned_columns
            for k, v in columns.items():
                if k in MPCC_SETTINGS.COMPONENTS:
                    scanned_columns.add(k)
                    continue

                nesting = k.count(".")
                if nesting > MPCC_SETTINGS.MAX_NESTING:
                    raise MPContribsClientError(
                        f"Nesting depth larger than {MPCC_SETTINGS.MAX_NESTING} for {k}!"
                    )

                for col in scanned_columns:
                    if nesting and col.startswith(k):
                        raise MPContribsClientError(
                            f"Duplicate definition of {k} in {col}!"
                        )

                    for n in range(1, nesting + 1):
                        if k.rsplit(".", n)[0] == col:
                            raise MPContribsClientError(
                                f"Ancestor of {k} already defined in {col}!"
                            )

                is_valid_string = isinstance(v, str) and v.lower() != "nan"
                if not is_valid_string and v is not None:
                    raise MPContribsClientError(
                        f"Unit '{v}' for {k} invalid (use `None` or a non-NaN string)!"
                    )

                if v != "" and v is not None and v not in ureg:
                    raise MPContribsClientError(f"Unit '{v}' for {k} not supported!")

                scanned_columns.add(k)

            # sort to avoid "overlapping columns" error in handsontable's NestedHeaders
            sorted_columns = flatten_dict(unflatten_dict(columns))
            # also sort by increasing nesting for better columns display
            sorted_columns = dict(
                sorted(sorted_columns.items(), key=lambda item: item[0].count("."))
            )

            # TODO catch unsupported column renaming or implement solution
            # reconcile with existing columns
            resp = self.get_project_by_name(name=name, fields=["columns"])
            existing_columns = {}

            for col in resp.columns:
                existing_columns[col.path] = col.model_dump().pop("path")

            for path, unit in sorted_columns.items():
                if path in MPCC_SETTINGS.COMPONENTS:
                    new_columns.append({"path": path})
                    continue

                full_path = f"data.{path}"
                new_column = {"path": full_path}
                existing_column = existing_columns.get(full_path)

                if unit is not None:
                    new_column["unit"] = unit

                if existing_column:
                    # NOTE if existing_unit == "NaN":
                    #   it was set by omitting "unit" in new_column
                    new_unit = new_column.get("unit", "NaN")
                    existing_unit = existing_column.get("unit")
                    if existing_unit != new_unit:
                        if existing_unit == "NaN" and new_unit == "":
                            factor = 1
                        else:
                            conv_args = []
                            for u in [existing_unit, new_unit]:
                                try:
                                    conv_args.append(ureg.Unit(u))
                                except ValueError:
                                    raise MPContribsClientError(
                                        f"Can't convert {existing_unit} to {new_unit} for {path}"
                                    )
                            try:
                                factor = ureg.convert(1, *conv_args)  # type: ignore[arg-type]
                            except DimensionalityError:
                                raise MPContribsClientError(
                                    f"Can't convert {existing_unit} to {new_unit} for {path}"
                                )

                        if not isclose(factor, 1):
                            MPCC_LOGGER.info(
                                f"Changing {existing_unit} to {new_unit} for {path} ..."
                            )
                            # TODO scale contributions to new unit
                            raise MPContribsClientError(
                                "Changing units not supported yet. Please resubmit"
                                " contributions or update accordingly."
                            )

                new_columns.append(new_column)

        payload = {"columns": new_columns}
        self._is_valid_payload(ContribsProject, payload)

        return self.update(update=payload, name=name)

    def validate_query_project(self, query: dict[str, Any]):
        if self.name:
            if "project" in query and self.name != query["project"]:
                raise MPContribsClientError(
                    f"client initialized with different project {self.name}!"
                )
            query["project"] = self.name
        else:
            if not query or "project" not in query:
                raise MPContribsClientError(
                    "initialize client with project, or include project in query!"
                )


class AsyncProjectResource(AsyncBaseResource, AsyncProjectProtocol):
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

    # Brendan TODO: Is it more idiomatic to prefer the newly supplied name and set self.name = name?
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
        self,
        name: str | None,
        fields: list[Any] | None,
        **kwargs,
    ) -> ContribsProject:
        """Get a project by referencing its name.

        Args:
            name (str): the name of the project to search. If self.name is not None, prefer to use that over the supplied name
            fields (list[str] | None): a list of fields to return. If none are supplied return all fields
            kwargs (dict): allows for pass-through of arguments for retry behavior
        """
        name = self._get_name(name)
        params: dict[str, str | list[str]] = {}
        params["_fields"] = ",".join(fields) if fields else ["_all"]
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
            url=str(self.url),
            item_model=ContribsProject,
            params=query,
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

    async def update(
        self, update: dict[str, Any], name: str | None = None
    ) -> ContribsProject:
        """Update project info.

        Args:
            update (dict): dictionary containing project info to update
            name (str): name of the project
        """
        if not update:
            MPCC_LOGGER.warning("nothing to update")
            raise MPContribsClientError("No update dict provided")

        name = self._get_name(name)

        disallowed = ["stats", "columns"]
        update = helpers.prune_dict(update, disallowed)
        if not update:
            raise MPContribsClientError(
                f"no valid keys given in udpate dict. Must not only contain {disallowed}"
            )

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
        self._is_valid_payload(ContribsProject, payload)
        resp = await self.put(path=f"{name}", project=payload)
        if not resp.get("count", 0):
            raise MPContribsClientError(resp)
        return resp

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

    async def get_unique_identifiers_flags(
        self, query: dict[str, Any] | None = None
    ) -> dict[str, bool]:
        """Retrieve values for `unique_identifiers` flags.

        See `client.available_query_params(resource="projects")` for available query parameters.

        Args:
            query (dict): query to select projects

        Returns:
            dict of str to bool, ex.:
            {"<project-name>": True|False, ...}
        """
        results = await self.query(query=query, fields=["name", "unique_identifiers"])
        return {p["name"]: p["unique_identifiers"] for p in results}

    async def init_columns(
        self, columns: dict | None = None, name: str | None = None
    ) -> ContribsProject:
        """Initialize columns for a project to set their order and desired units.

        The `columns` field of a project tracks the minima and maxima of each `data` field
        in its contributions. If columns are not initialized before submission using this
        function, `submit_contributions` will respect the order of columns as they are
        submitted and will try to auto-determine suitable units.

        `init_columns` can be used at any point to reset the order of columns. Omitting
        the `columns` argument will re-initialize columns based on the `data` fields of
        all submitted contributions.

        The `columns` argument is a dictionary which maps the data field names to its
        units. Use `None` to indicate that a field is not a quantity (plain string). The
        unit for a dimensionless quantity is an empty string (""). Percent (`%`) and
        permille (`%%`) are considered units. Nested fields are indicated using a dot
        (".") in the data field name.

        Example:
        >>> client.init_columns({"a": None, "b.c": "eV", "b.d": "mm", "e": ""})

        This example will result in column headers on the project landing page of the form


        |      |      data       |      |
        | data |        b        | data |
        |   a  | c [eV] | d [mm] | e [] |


        Args:
            columns (dict): dictionary mapping data column to its unit
            name (str or None) : optional name of the project to use,
                defaults to `self.project`.

        Returns:
            dict containing metadata about the column updates
        """
        name = self._get_name(name)

        columns = flatten_dict(columns or {})

        if len(columns) > MPCC_SETTINGS.MAX_COLUMNS:
            raise MPContribsClientError(
                f"Number of columns larger than {MPCC_SETTINGS.MAX_COLUMNS}!"
            )

        if not all(isinstance(v, str) for v in columns.values() if v is not None):
            raise MPContribsClientError(
                "All values in `columns` need to be None or of type str!"
            )

        new_columns = []

        if columns:
            # check columns input
            scanned_columns = set()

            # Gets valid column names into scanned_columns
            for k, v in columns.items():
                if k in MPCC_SETTINGS.COMPONENTS:
                    scanned_columns.add(k)
                    continue

                nesting = k.count(".")
                if nesting > MPCC_SETTINGS.MAX_NESTING:
                    raise MPContribsClientError(
                        f"Nesting depth larger than {MPCC_SETTINGS.MAX_NESTING} for {k}!"
                    )

                for col in scanned_columns:
                    if nesting and col.startswith(k):
                        raise MPContribsClientError(
                            f"Duplicate definition of {k} in {col}!"
                        )

                    for n in range(1, nesting + 1):
                        if k.rsplit(".", n)[0] == col:
                            raise MPContribsClientError(
                                f"Ancestor of {k} already defined in {col}!"
                            )

                is_valid_string = isinstance(v, str) and v.lower() != "nan"
                if not is_valid_string and v is not None:
                    raise MPContribsClientError(
                        f"Unit '{v}' for {k} invalid (use `None` or a non-NaN string)!"
                    )

                if v != "" and v is not None and v not in ureg:
                    raise MPContribsClientError(f"Unit '{v}' for {k} not supported!")

                scanned_columns.add(k)

            # sort to avoid "overlapping columns" error in handsontable's NestedHeaders
            sorted_columns = flatten_dict(unflatten_dict(columns))
            # also sort by increasing nesting for better columns display
            sorted_columns = dict(
                sorted(sorted_columns.items(), key=lambda item: item[0].count("."))
            )

            # TODO catch unsupported column renaming or implement solution
            # reconcile with existing columns
            resp = await self.get_project_by_name(name=name, fields=["columns"])
            existing_columns = {}

            for col in resp.columns:
                existing_columns[col.path] = col.model_dump().pop("path")

            for path, unit in sorted_columns.items():
                if path in MPCC_SETTINGS.COMPONENTS:
                    new_columns.append({"path": path})
                    continue

                full_path = f"data.{path}"
                new_column = {"path": full_path}
                existing_column = existing_columns.get(full_path)

                if unit is not None:
                    new_column["unit"] = unit

                if existing_column:
                    # NOTE if existing_unit == "NaN":
                    #   it was set by omitting "unit" in new_column
                    new_unit = new_column.get("unit", "NaN")
                    existing_unit = existing_column.get("unit")
                    if existing_unit != new_unit:
                        if existing_unit == "NaN" and new_unit == "":
                            factor = 1
                        else:
                            conv_args = []
                            for u in [existing_unit, new_unit]:
                                try:
                                    conv_args.append(ureg.Unit(u))
                                except ValueError:
                                    raise MPContribsClientError(
                                        f"Can't convert {existing_unit} to {new_unit} for {path}"
                                    )
                            try:
                                factor = ureg.convert(1, *conv_args)  # type: ignore[arg-type]
                            except DimensionalityError:
                                raise MPContribsClientError(
                                    f"Can't convert {existing_unit} to {new_unit} for {path}"
                                )

                        if not isclose(factor, 1):
                            MPCC_LOGGER.info(
                                f"Changing {existing_unit} to {new_unit} for {path} ..."
                            )
                            # TODO scale contributions to new unit
                            raise MPContribsClientError(
                                "Changing units not supported yet. Please resubmit"
                                " contributions or update accordingly."
                            )

                new_columns.append(new_column)

        payload = {"columns": new_columns}
        self._is_valid_payload(ContribsProject, payload)

        return await self.update(update=payload, name=name)

    def validate_query_project(self, query: dict[str, Any]):
        if self.name:
            if "project" in query and self.name != query["project"]:
                raise MPContribsClientError(
                    f"client initialized with different project {self.name}!"
                )
            query["project"] = self.name
        else:
            if not query or "project" not in query:
                raise MPContribsClientError(
                    "initialize client with project, or include project in query!"
                )
