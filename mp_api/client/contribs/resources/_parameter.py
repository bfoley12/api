from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class _ParamSchema(BaseModel):
    default: Any | None = None
    maximum: int | None = None


class _Parameter(BaseModel):
    name: str
    description: str
    param_in: str = Field(alias="in")
    # Brendan TODO: Can make this an Enum
    type: str | None = None
    # OpenAPI 3.x: constraints live under `schema`
    schema_: _ParamSchema | None = Field(default=None, alias="schema")
    # Swagger 2.0: constraints live on the parameter itself
    default: Any | None = None
    maximum: int | None = None

    def limits(self) -> tuple[int, int] | None:
        d = self.schema_.default if self.schema_ else self.default
        m = self.schema_.maximum if self.schema_ else self.maximum
        return (d, m) if d is not None and m is not None else None
