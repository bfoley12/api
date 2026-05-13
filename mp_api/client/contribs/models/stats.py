from __future__ import annotations

from mp_api.client.core.schemas import _DictLikeAccess


class Stats(_DictLikeAccess):
    """Define aggregated project statistics schema."""

    columns: int = 0
    contributions: int = 0
    tables: int = 0
    structures: int = 0
    attachments: int = 0
    size: float = 0.0
