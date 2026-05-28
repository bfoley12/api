from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import AfterValidator, model_validator

from mp_api.client.contribs.utils import get_md5
from mp_api.client.core.schemas import _DictLikeAccess


# TODO: Find new name: conflicts with BaseContrib
# This might end up being unnecessary
class ContribsBase(_DictLikeAccess):
    pass


_MD5 = re.compile(r"^[a-f0-9]{32}$")


def _validate_md5(v: str) -> str:
    v = v.lower()
    if not _MD5.match(v):
        raise ValueError("must be a 32-character MD5 hex digest")
    return v


Md5Hash = Annotated[str, AfterValidator(_validate_md5)]


class ContributionsSupplemental(_DictLikeAccess):
    id: str | None = None
    name: str
    md5: Md5Hash

    @model_validator(mode="before")
    def generate_md5(cls, data: dict[str, Any]) -> dict[str, Any]:
        if "md5" not in data:
            data["md5"] = get_md5(data)
        return data
