from __future__ import annotations

from pydantic import Field
from pydantic.dataclasses import dataclass


@dataclass
class UpsertResponse:
    new_ids: list[str] = Field(default_factory=list)
    num_updated: int = 0
