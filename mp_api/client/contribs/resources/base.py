from __future__ import annotations

import asyncio
import math
from copy import deepcopy
from enum import StrEnum
from functools import cached_property
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from mp_api.client.contribs import helpers
from mp_api.client.contribs.pagination import PageMeta
from mp_api.client.contribs.resources._parameter import _Parameter
from mp_api.client.contribs.retry import standard_retry, standard_timeout
from mp_api.client.core.exceptions import MPContribsClientError


class VALID_RESOURCES(StrEnum):
    PROJECTS = "projects"
    CONTRIBUTIONS = "contributions"


class AsyncBaseResource:
    """Shared HTTP behavior. Does not own the pool."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        use_document_model: bool = True,
        endpoint_slug: str = "",
    ) -> None:
        """Common fields for all Resources.

        Args:
            http (httpx.Client): the client to use within the resource
            use_document_model (bool): whether the class should return Pydantic models (True) or MPCDicts (False)
            endpoint_slug (str): the endpoint we are targeting that all methods build on
                ie for projects: url/projects/*, where "projects" is the endpoint_slug
        """
        self.http = http
        self.use_document_model = use_document_model
        self.endpoint_slug: str = endpoint_slug

    @cached_property
    async def _per_page_table(self) -> dict[str, tuple[int, int]]:
        """OperationId -> (default, max) for its per_page parameter."""
        spec = (await self.http.get("openapi.json")).raise_for_status().json()
        table: dict[str, tuple[int, int]] = {}
        for path_item in spec.get("paths", {}).values():
            for method_obj in path_item.values():
                if not isinstance(method_obj, dict):
                    continue  # skip "parameters", "summary", etc. at path level
                op_id = method_obj.get("operationId")
                if not op_id:
                    continue
                for raw in method_obj.get("parameters", []):
                    param = _Parameter.model_validate(raw)
                    if param.name == "per_page" and (lim := param.limits()):
                        table[op_id] = lim
                        break
        return table

    @standard_timeout(seconds=5)
    @standard_retry
    async def _request(self, method: str, path: str, **kwargs) -> Any:
        r = await self.http.request(method, f"{self.endpoint_slug}/{path}", **kwargs)
        r.raise_for_status()
        return r.json()

    async def get(self, path="", **kwargs) -> Any:
        return await self._request("GET", path, **kwargs)

    async def post(self, path="", **kwargs) -> Any:
        return await self._request("POST", path, **kwargs)

    async def put(self, path="", **kwargs) -> Any:
        return await self._request("PUT", path, **kwargs)

    async def patch(self, path="", **kwargs) -> Any:
        return await self._request("PATCH", path, **kwargs)

    async def delete(self, path="", **kwargs) -> Any:
        return await self._request("DELETE", path, **kwargs)

    async def _get_per_page_default_max(
        self,
        op: helpers.VALID_OPS = helpers.VALID_OPS.QUERY,
        resource: VALID_RESOURCES = VALID_RESOURCES.CONTRIBUTIONS,
    ) -> tuple[int, int]:
        op_id = f"{op}{resource.capitalize()}"
        try:
            return (await self._per_page_table)[op_id]
        except KeyError:
            raise MPContribsClientError(
                f"No per_page limits found for operation {op_id!r}. "
                f"Either the spec is missing them or the operationId is wrong."
            )

    # Brendan TODO: Old method, can probably modernize
    async def _split_query(
        self,
        query: dict[str, Any],
        op: helpers.VALID_OPS = helpers.VALID_OPS.QUERY,
        resource: VALID_RESOURCES = VALID_RESOURCES.CONTRIBUTIONS,
        pages: int = -1,
    ) -> list[dict]:
        """Avoid URI too long errors."""
        pp_default, pp_max = await self._get_per_page_default_max(
            op=op, resource=resource
        )
        per_page = pp_default if any(k.endswith("__in") for k in query) else pp_max
        nr_params_to_split = sum(
            len(v) > per_page for v in query.values() if isinstance(v, list)
        )
        if nr_params_to_split > 1:
            raise MPContribsClientError(
                f"More than one list in query with length > {per_page} not supported!"
            )

        queries: list[dict[str, Any]] = []

        for k, v in query.items():
            if isinstance(v, list):
                line_len = len(",".join(v).encode("utf-8"))

                while line_len > 3800:
                    per_page = int(0.8 * per_page)
                    vv = v[:per_page]
                    line_len = len(",".join(vv).encode("utf-8"))

                if len(v) > per_page:
                    for chunk in helpers.grouper(per_page, v):
                        queries.append({k: list(chunk)})

        query["per_page"] = per_page

        if not queries:
            queries = [query]

        if len(queries) == 1 and pages and pages > 0:
            queries = []
            for page in range(1, pages + 1):
                queries.append(deepcopy(query))
                queries[-1]["page"] = page

        for q in queries:
            # copy over missing parameters
            q.update({k: v for k, v in query.items() if k not in q})

            # comma-separated lists
            q.update({k: ",".join(v) for k, v in q.items() if isinstance(v, list)})

        return queries

    async def scan(
        self,
        query: dict[str, Any] | None = None,
        resource: VALID_RESOURCES = VALID_RESOURCES.CONTRIBUTIONS,
        _timeout: int = -1,
        op: helpers.VALID_OPS = helpers.VALID_OPS.QUERY,
        *,
        name: str | None = None,
    ) -> tuple[int, int]:
        """Return (total_count, total_pages) for a query without fetching rows."""
        query = query or {}

        if name and "project" not in query:
            query["project"] = name

        skip_keys = {"per_page", "_fields", "format", "_sort"}
        query = {k: v for k, v in query.items() if k not in skip_keys}
        query["_fields"] = []  # only need totals -> explicitly request no fields
        subqueries = await self._split_query(query, op=op, resource=resource)

        results = await asyncio.gather(*(self._probe(q) for q in subqueries))
        total_count = sum(c for c, _ in results)
        total_pages = sum(p for _, p in results)
        return total_count, total_pages

    async def _probe(self, q: dict) -> tuple[int, int]:
        real_per_page = q["per_page"]
        params = {**q, "per_page": 1, "page": 1}
        resp = await self.http.get("", params=params)
        resp.raise_for_status()
        meta = PageMeta.model_validate(resp.json()["meta"])
        return meta.total_count, math.ceil(meta.total_count / real_per_page)

    def _is_valid_payload(self, model: BaseModel, data: dict[str, Any]) -> None:
        """Raise an error if a payload is invalid."""
        model_spec = model.model_json_schema()
        model_spec.pop("required")
        model_spec["additionalProperties"] = False

        try:
            _ = model.model_validate(data, strict=True)
        except ValidationError as ex:
            raise MPContribsClientError(str(ex))
