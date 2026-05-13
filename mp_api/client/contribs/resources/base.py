from __future__ import annotations

from typing import Any

import httpx

from mp_api.client.contribs.retry import standard_retry


class BaseResource:
    """Shared HTTP behavior. Does not own the pool."""

    def __init__(self, http: httpx.Client, use_document_model: bool = False) -> None:
        self.http = http
        self.use_document_model = use_document_model

    @standard_retry
    def _request(self, method: str, path: str, **kwargs) -> Any:
        r = self.http.request(method, path, **kwargs)
        r.raise_for_status()
        return r.json()

    def get(self, path, **kw):
        return self._request("GET", path, **kw)

    def post(self, path, **kw):
        return self._request("POST", path, **kw)

    def put(self, path, **kw):
        return self._request("PUT", path, **kw)

    def patch(self, path, **kw):
        return self._request("PATCH", path, **kw)

    def delete(self, path, **kw):
        return self._request("DELETE", path, **kw)
