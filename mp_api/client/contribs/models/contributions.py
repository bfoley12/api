from __future__ import annotations

from typing import Any, Self, cast, get_args

import pandas as pd
from emmet.core.types.typing import DateTimeType
from pydantic import field_serializer, field_validator
from pymatgen.core import Structure

from mp_api.client.contribs.models.attachments import Attachments
from mp_api.client.contribs.models.base import ContribsBase
from mp_api.client.contribs.models.tables import Table
from mp_api.client.contribs.schemas import Datum, _get_pydantic_from_dataframe
from mp_api.client.contribs.utils import flatten_dict, unflatten_dict


class Contribution(ContribsBase):
    """Define base schema for a single contribution."""

    id: str | None = None
    project: str | None = None
    identifier: str | None = None
    formula: str | None = None
    is_public: bool = False
    last_modified: DateTimeType
    needs_build: bool = True
    data: dict[str, str | bool | Datum | None] = {}
    structures: list[Structure] | None = None
    tables: list[Table] | None = None
    attachments: list[Attachments] | None = None

    @field_validator("data", mode="before")
    def construct_data(cls, d: dict) -> dict[str, str | Datum]:
        if all(isinstance(v, str | Datum) for v in d.values()):
            return d
        flattened_data_dct = flatten_dict(d)
        unique_keys = {
            (
                k.rsplit(".", 1)[0]
                if k.rsplit(".", 1)[-1] in {"value", "error", "unit", "display"}
                else k
            )
            for k in flattened_data_dct
        }
        return {
            k: (
                Datum(  # type: ignore[misc]
                    **{
                        sub_k: flattened_data_dct.get(f"{k}.{sub_k}", field.default)
                        for sub_k, field in Datum.model_fields.items()
                    }
                )
                if f"{k}.value" in flattened_data_dct
                else flattened_data_dct.get(k)
            )
            for k in unique_keys
        }

    @property
    def id_fields(self) -> set[str]:
        return {k for k in [self.id, self.project, self.identifier] if k}

    @staticmethod
    def id_keys() -> set[str]:
        return {"id", "project", "identifier"}

    @field_serializer("data", mode="plain")
    def unflatten_data(self, x: dict[str, str | Datum]) -> dict[str, Any]:
        return unflatten_dict(
            {
                k: cast(Datum, v).model_dump() if hasattr(v, "model_dump") else v
                for k, v in x.items()
            },
        )


class ContributionSubmission(Contribution):
    """Schema for user-submitted contributions.

    NB: We forbid submission of new attachments.
    """

    @classmethod
    def from_dataframe(
        cls, df: pd.DataFrame, project: str = "PLACEHOLDER", **kwargs
    ) -> list[Self]:
        """Construct a contribution from a DataFrame."""
        base_model, columns_renamed = _get_pydantic_from_dataframe(df)

        non_null_typs = {}
        for k, field in base_model.model_fields.items():
            try:
                non_null_typs[k] = next(
                    t for t in get_args(field.annotation) if t is not None
                )
            except StopIteration:
                non_null_typs[k] = field.annotation

        # sanitize data
        sanitized = [
            base_model(
                **{
                    columns_renamed[k]: (
                        non_null_typs[columns_renamed[k]](v) if not pd.isna(v) else None
                    )
                    for k, v in row.to_dict().items()
                }
            ).model_dump()
            for _, row in df.iterrows()
        ]

        non_num_fields = {
            k for k, typ in non_null_typs.items() if typ not in (int, float)
        }

        return [
            cls(  # type: ignore[call-arg]
                identifier=str(idx),
                project=project,
                data={
                    k: (
                        entry.get(k)
                        if (k in non_num_fields or entry.get(k) is None)
                        else Datum(value=entry.get(k), unit=field.description or "")  # type: ignore[arg-type]
                    )
                    for k, field in base_model.model_fields.items()
                },
            )
            for idx, entry in enumerate(sanitized)
        ]

    def to_submission(self) -> dict[str, Any]:
        """Pop null keys."""
        return {
            k: v
            for k, v in self.model_dump(mode="json").items()
            if v is not None and k != "id"
        }
