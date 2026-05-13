from __future__ import annotations

from typing import Any

import httpx
from pydantic import JsonValue, model_validator

from mp_api.client.contribs._logger import MPCC_LOGGER
from mp_api.client.core.schemas import _DictLikeAccess


# Brendan TODO: Find a better name
class Response(_DictLikeAccess):
    result: JsonValue | bytes
    count: int
    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="before")
    @classmethod
    def from_httpx(cls, data: Any) -> dict[str, Any]:
        # Pass-through if already a dict (model construction from plain data)
        if isinstance(data, dict):
            return data
        if not isinstance(data, httpx.Response):
            raise TypeError(
                f"expected httpx.Response or dict, got {type(data).__name__}"
            )

        resp = data
        content_type = resp.headers.get("content-type", "")

        if content_type.startswith("application/json"):
            payload = resp.json()
            if isinstance(payload, dict):
                if "warning" in payload:
                    MPCC_LOGGER.warning(payload["warning"])
                if isinstance(payload.get("error"), str):
                    MPCC_LOGGER.error(payload["error"][:10000] + "...")

                if isinstance(payload.get("data"), list):
                    return {"result": payload, "count": len(payload["data"])}
                if isinstance(payload.get("count"), int):
                    return {"result": payload, "count": payload["count"]}
                return {"result": payload, "count": 1}

            if isinstance(payload, list):
                return {"result": payload, "count": len(payload)}

            return {"result": payload, "count": 1}

        if content_type.startswith("application/gzip"):
            return {"result": resp.content, "count": 1}

        MPCC_LOGGER.error(f"request failed with status {resp.status_code}!")
        return {"result": None, "count": 0}
