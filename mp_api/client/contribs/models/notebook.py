from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mp_api.client.contribs.models.base import ContribsBase


class NotebookOutputData(BaseModel):
    text_plain: str = Field(alias="text/plain")
    text_html: str = Field(alias="text/html")


class NotebookOutput(BaseModel):
    data: NotebookOutputData | None = None
    name: str | None = None
    text: str | None = None
    # Todo: find example of metadata, maybe make a class
    metadata: dict[str, Any] | None = None
    # TODO: This could probably be enumerated
    output_type: str


class NotebookCell(BaseModel):
    id: str
    # TODO: Could enumerate
    cell_type: str
    metadata: dict[str, Any]
    execution_count: int
    source: str
    # Brendan TODO: Outputs seem to always come in a pair: the first is more metadata-esque,
    # while the second contains the data, metadata (have not seen this be non-empty) and output type
    outputs: list[NotebookOutput] | None = None


class Notebook(ContribsBase):
    id: str
    nbformat: int
    nbformat_minor: int
    metadata: dict[str, Any]
    cells: list[NotebookCell]
