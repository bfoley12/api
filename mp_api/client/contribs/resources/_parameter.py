from __future__ import annotations

from pydantic import BaseModel, Field


class _ParamSchema(BaseModel):
    default: int | None = None
    maximum: int | None = None


class _Parameter(BaseModel):
    name: str
    # OpenAPI 3.x: constraints live under `schema`
    schema_: _ParamSchema | None = Field(default=None, alias="schema")
    # Swagger 2.0: constraints live on the parameter itself
    default: int | None = None
    maximum: int | None = None

    def limits(self) -> tuple[int, int] | None:
        d = self.schema_.default if self.schema_ else self.default
        m = self.schema_.maximum if self.schema_ else self.maximum
        return (d, m) if d is not None and m is not None else None
