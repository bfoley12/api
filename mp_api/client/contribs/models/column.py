from __future__ import annotations

from mp_api.client.core.schemas import _DictLikeAccess


class Column(_DictLikeAccess):
    """Define schema of MP Contribs column statistics."""

    path: str
    min: float | None = float("nan")
    max: float | None = float("nan")
    unit: str = "NaN"
