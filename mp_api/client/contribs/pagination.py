# pagination.py
from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator
from typing import TypeVar

import httpx
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class PageMeta(BaseModel):
    total_count: int
    total_pages: int
    per_page: int
    page: int


class Page[T: BaseModel](BaseModel):
    """Default page envelope. Subclass if your API uses different field names."""

    items: list[T]
    total: int

    def page_count(self, per_page: int) -> int:
        return math.ceil(self.total / per_page) if per_page else 1


class Paginator[T: BaseModel]:
    def __init__(
        self,
        client: httpx.AsyncClient,
        url: str,
        page_model: type[Page[T]],
        *,
        params: dict | None = None,
        per_page: int = 100,
        page_param: str = "page",
        per_page_param: str = "per_page",
        start_page: int = 1,
        max_concurrency: int = 10,
    ) -> None:
        """Create an instance of Paginator.

        Handles pagination of results.
        """
        self.client = client
        self.url = url
        self.page_model = page_model
        self.base_params = params or {}
        self.per_page = per_page
        self.page_param = page_param
        self.per_page_param = per_page_param
        self.start_page = start_page
        self._sem = asyncio.Semaphore(max_concurrency)

    async def _fetch(self, page: int) -> Page[T]:
        async with self._sem:
            r = await self.client.get(
                self.url,
                params={
                    **self.base_params,
                    self.page_param: page,
                    self.per_page_param: self.per_page,
                },
            )
            r.raise_for_status()
            return self.page_model.model_validate(r.json())

    async def all(self) -> list[T]:
        """Fetch page 1, then dispatch the rest concurrently."""
        first = await self._fetch(self.start_page)
        n_pages = first.page_count(self.per_page)
        if n_pages <= 1:
            return list(first.items)

        rest = await asyncio.gather(
            *(
                self._fetch(p)
                for p in range(self.start_page + 1, self.start_page + n_pages)
            )
        )
        out = list(first.items)
        for page in rest:
            out.extend(page.items)
        return out

    async def __aiter__(self) -> AsyncIterator[T]:
        """Stream items sequentially — lighter memory, preserves order."""
        page_num = self.start_page
        while True:
            page = await self._fetch(page_num)
            for item in page.items:
                yield item
            consumed = (page_num - self.start_page + 1) * self.per_page
            if consumed >= page.total:
                return
            page_num += 1


async def paginate[T: BaseModel](
    client: httpx.AsyncClient,
    url: str,
    item_model: type[T],
    **kwargs,
) -> list[T]:
    """Convenience function for default pagination."""
    return await Paginator(client, url, Page[item_model], **kwargs).all()
