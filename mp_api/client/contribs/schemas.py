"""Define data models used when querying the client."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pandas as pd
from pydantic import BaseModel, Field, create_model

from mp_api.client.contribs.models.contributions import Contribution
from mp_api.client.core.schemas import _DictLikeAccess

if TYPE_CHECKING:
    from types import UnionType

CONTRIBS_DOC_NAME = "ContribsDoc"
"""Parent name of the dynamically-created contribs docs, similar to `MPDataDoc`."""


def _cast_pandas_dtype(dtype: type, assume_nullable: bool = True) -> type | UnionType:
    """Convert pandas dtype to built-in types.

    Args:
        dtype (type) : pandas dtype to convert to builtin (ex., pd.Float64)
        assume_nullable (bool) : whether to assume that a cast type can be nullable.

    Returns:
        type

    Adapted from mpcontribs-lux.
    """
    vname: str = getattr(dtype, "name", str(dtype)).lower()
    inferred_type: type = str
    if "float" in vname:
        inferred_type = float
    elif "int" in vname:
        inferred_type = int
    elif "bool" in vname:
        inferred_type = bool
    return inferred_type | None if assume_nullable else inferred_type


def _get_unit(v: str) -> tuple[str, str | None]:
    """Parse a physical variable name and its optional unit from a string value.

    Ex:
        _get_unit("Temperature [K]") or _get_unit("Temperature (K)")
        will both return "Temperature", "K"

    Args:
        v (str) : input column name to parse

    Returns:
        str : the base name of the physical quantity
        str or None: its optional unit
    """
    if (matched := re.search(r"\(([^)]+)\)|\[([^\]]+)\]", v)) is not None:
        try:
            unit_group = next(
                i for i, x in enumerate(matched.groups()) if x is not None
            )
            unit = matched.groups()[unit_group]
            splitter = f"({unit})" if unit_group == 0 else f"[{unit}]"
            return v.split(splitter, 1)[0].strip(), unit
        except StopIteration:
            pass
    return v, None


def _to_camel_case(v: str) -> str:
    """Convert a generic string to CamelCase.

    Args:
        v (str) : input string

    Returns:
        str : CamelCase string
    """
    split_strs = [y for x in v.lower().split() for y in x.split("_")]
    return "".join(s[0].upper() + s[1:] for s in split_strs)


def _get_pydantic_from_dataframe(
    df: pd.DataFrame,
) -> tuple[type[BaseModel], dict[str, str]]:
    """Dynamically create a pydantic BaseModel from a pandas DataFrame.

    Args:
        df : pandas DataFrame to parse

    Returns:
        BaseModel: the inferred schema of the pandas DataFrame
        dict of str to str: the remapped column names in an
            MP Contribs compatible format.
    """
    columns_renamed = {}
    columns_to_unit = {}
    character_replacements = str.maketrans(
        {
            "^": "**",
            ":": "",
            "#": "",
        }
    )
    for col in df.columns:
        base_name, unit = _get_unit(col)
        base_name = _to_camel_case(base_name)
        columns_renamed[col] = base_name.translate(character_replacements)
        if unit:
            columns_to_unit[col] = unit

    for col in (c for c, v in columns_to_unit.items() if v is None):
        _ = columns_to_unit.pop(col)

    model_fields: dict[str, Any] = {
        columns_renamed[col_name]: (
            _cast_pandas_dtype(
                df.dtypes[col_name],
                assume_nullable=any(pd.isna(df[col_name])),
            ),
            Field(default=None, description=columns_to_unit.get(col_name)),
        )
        for col_name in df.columns
        if not all(pd.isna(df[col_name]))
    }

    return create_model(
        "InferredModel", __base__=_DictLikeAccess, **model_fields
    ), columns_renamed  # type: ignore[call-overload]


class Datum(_DictLikeAccess):
    """Define schema for numeric contribution data."""

    value: int | float
    error: int | float | None = None
    unit: str = ""

    @property
    def display_name(self) -> str:
        """Format for display."""
        return (
            f"{self.value}"
            + (f" ± {self.error}" if self.error is not None else "")
            + (f" {self.unit}" if self.unit else "")
        )

    def __str__(self) -> str:
        """Format for display."""
        return self.display_name

    def __repr__(self) -> str:
        """Format for display."""
        return self.display_name

    def __float__(self) -> float:
        """Allow conversion to float."""
        return float(self.value)

    def __int__(self) -> int:
        """Allow conversion to int."""
        return int(self.value)


class QueryResult(_DictLikeAccess):
    """Result of query_contributions."""

    total_count: int
    total_pages: int
    data: list[Contribution] | None = None
    has_more: bool = False
