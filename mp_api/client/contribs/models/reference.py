from __future__ import annotations

from mp_api.client.core.schemas import _DictLikeAccess


class Reference(_DictLikeAccess):
    """Define schema of URL reference."""

    label: str
    url: str
