from __future__ import annotations

from typing import Any

import httpx

from mp_api.client.contribs.retry import standard_retry


class BaseResource:
    """Shared HTTP behavior. Does not own the pool."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        use_document_model: bool = False,
        endpoint_slug: str = "",
    ) -> None:
        """Common fields for all Resources.

        Args:
            http (httpx.Client): the client to use within the resource
            use_document_model (bool): whether the class should return Pydantic models (false) or MPCDicts (true)
            endpoint_slug (str): the endpoint we are targeting that all methods build on
                ie for projects: url/projects/*, where "projects" is the endpoint_slug
        """
        self.http = http
        self.use_document_model = use_document_model
        self.endpoint_slug: str = endpoint_slug

    @standard_retry
    def _request(self, method: str, path: str, **kwargs) -> Any:
        r = self.http.request(method, f"{self.endpoint_slug}/{path}", **kwargs)
        r.raise_for_status()
        return r.json()

    def get(self, path="", **kw) -> Any:
        return self._request("GET", path, **kw)

    def post(self, path="", **kw) -> Any:
        return self._request("POST", path, **kw)

    def put(self, path="", **kw) -> Any:
        return self._request("PUT", path, **kw)

    def patch(self, path="", **kw) -> Any:
        return self._request("PATCH", path, **kw)

    def delete(self, path="", **kw) -> Any:
        return self._request("DELETE", path, **kw)
