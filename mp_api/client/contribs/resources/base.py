from __future__ import annotations

from enum import StrEnum
from typing import Any

import httpx

from mp_api.client.contribs.retry import standard_retry, standard_timeout


class VALID_RESOURCES(StrEnum):
    PROJECTS = "projects"
    CONTRIBUTIONS = "contributions"


class BaseResource:
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
