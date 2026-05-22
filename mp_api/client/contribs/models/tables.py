from __future__ import annotations

import polars as pl
from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    model_validator,
)

from mp_api.client.contribs.models.base import ContributionsSupplemental


class Labels(BaseModel):
    index: str
    value: str
    variable: str


class Attributes(BaseModel):
    title: str
    labels: Labels


class TableStub(ContributionsSupplemental):
    """Metadata-only table as embedded in contribution responses (no data)."""

    attrs: Attributes
    columns: list[str]
    total_data_rows: int
    total_data_pages: int = 1


class Table(ContributionsSupplemental):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    attrs: Attributes
    total_data_rows: int
    data: pl.DataFrame

    @model_validator(mode="after")
    def data_dimensions(self):
        if len(self.data) != self.total_data_rows:
            raise ValidationError(
                f"`total_data_rows` ({self.total_data_rows}) does not match "
                f"number of rows in `data` ({len(self.data)})"
            )
        return self

    @staticmethod
    def _check_column_collision(columns: list[str], index_name: str) -> None:
        if index_name in columns:
            raise ValidationError(
                f"column name collision: {index_name!r} already in columns"
            )

    @staticmethod
    def _check_index_data_lengths(index: list, data: list[list]) -> None:
        if len(index) != len(data):
            raise ValidationError(
                f"length mismatch between `index` ({len(index)}) "
                f"and `data` ({len(data)})"
            )

    @staticmethod
    def _check_declared_row_count(declared: int, data: list[list]) -> None:
        if declared != len(data):
            raise ValidationError(
                f"`total_data_rows` ({declared}) does not match "
                f"length of `data` ({len(data)}) in source document"
            )

    @classmethod
    def _validate_mongo_doc(cls, doc, index_name: str) -> None:
        cls._check_column_collision(doc["columns"], index_name)
        cls._check_index_data_lengths(doc["index"], doc["data"])
        cls._check_declared_row_count(doc["total_data_rows"], doc["data"])

    @classmethod
    def from_mongo(cls, doc, index_name: str = "index"):
        cls._validate_mongo_doc(doc, index_name)

        columns = [index_name, *doc["columns"]]

        # Strict=false since we explicitly handle our own errors
        rows = [
            [idx, *row] for idx, row in zip(doc["index"], doc["data"], strict=False)
        ]
        df = pl.DataFrame(rows, schema=columns, orient="row")

        return cls(
            name=doc["name"],
            md5=doc["md5"],
            attrs=doc["attrs"],
            data=df,
            total_data_rows=doc["total_data_rows"],
        )
