from __future__ import annotations

from typing import Any

from mp_api.client.contribs.models.project import ContribsProject
from mp_api.client.contribs.resources.base import BaseResource
from mp_api.client.contribs.resources.mpc import format_output


class ProjectResource(BaseResource):
    @format_output
    def get_project_by_name(self, name: str, fields: list[Any] | None):
        params: dict[str, str | list[str]] = {}
        if fields is not None:
            params["_fields"] = ",".join(fields)
        else:
            fields = ["_all"]
        r = self.http.get(f"/projects/{name}", params=params)
        r.raise_for_status()
        return ContribsProject.model_validate(r.json())
