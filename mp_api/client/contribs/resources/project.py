from __future__ import annotations

from mp_api.client.contribs.client import ContribsClient
from typing import Any

class ProjectClient:
    def __init__(self, client: ContribsClient):
        """Client for Project-related requests.

        Args:
            client (ContribsClient): the parent client to manage connections
        """
        self.client = client

    def get_project_by_name(self, name: str, fields: list[Any] | None):
        params: dict[str, str | list[str]] = {}
        if fields is not None:
            params["_fields"] = ",".join(fields)
        else:
            fields = ["_all"]
        r = self.client._http.get(f"/projects/{name}", params=params)
        r.raise_for_status()
        return Project.model_validate(r.json())
