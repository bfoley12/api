# pagination.py
from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator
from functools import cache
from typing import TypeVar

import httpx
from pydantic import BaseModel, Field, model_validator

T = TypeVar("T", bound=BaseModel)


class PageMeta(BaseModel):
    total_count: int | None = None
    total_pages: int | None = None
    per_page: int | None = None
    page: int | None = None
    has_more: bool | None = None


class Page[T: BaseModel](BaseModel):
    """Default page envelope: ``{meta: {...}, data: [...]}``."""

    meta: PageMeta
    data: list[T] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _lift_meta(cls, values):
        if isinstance(values, dict) and "meta" not in values:
            values = dict(values)
            values["meta"] = {
                "total_count": values.pop("total_count", None),
                "total_pages": values.pop("total_pages", None),
                "has_more": values.pop("has_more", None),
                "per_page": values.pop("per_page", None),
                "page": values.pop("page", None),
            }
        return values

    # Interface expected by Paginator. Kept as properties so the rest of
    # the class doesn't need to know the envelope shape.
    @property
    def items(self) -> list[T]:
        return self.data

    @property
    def total(self) -> int:
        return self.meta.total_count if self.meta.total_count else 0

    def page_count(self, per_page: int) -> int:
        total_count = self.meta.total_count if self.meta.total_count else 0
        return math.ceil(total_count / per_page) if per_page else 1


@cache
def _page_model_for(item_model: type[BaseModel]) -> type[Page]:
    """Cache parameterized Page[item_model] construction."""
    return Page[item_model]


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
        timeout: float | None = None,
        return_exceptions: bool = False,
        url_byte_budget: int = 3800,
    ) -> None:
        """Paginate a REST endpoint.

        Args:
            client: An ``httpx.AsyncClient`` used to issue requests. The
                paginator does not own the client and will not close it.
            url: The endpoint URL to paginate. May be absolute or relative
                to the client's ``base_url``.
            page_model: The Pydantic model class used to parse each page
                response. Typically ``Page[YourItemModel]``; must expose
                ``items`` and ``total`` fields.
            params: Base query-string parameters sent with every request.
                List values are joined with commas at request time. If a
                list's joined byte length exceeds ``url_byte_budget``, it is
                split across multiple parameter sets (see ``url_byte_budget``).
            per_page: Page size sent as the ``per_page_param`` value.
                Defaults to 100.
            page_param: Name of the page-number query parameter. Defaults
                to ``"page"``.
            per_page_param: Name of the page-size query parameter. Defaults
                to ``"per_page"``.
            start_page: Page number of the first page. Defaults to 1; set
                to 0 for APIs that use zero-based indexing.
            max_concurrency: Maximum number of in-flight requests across
                ``all()`` and the async iterator. Enforced via a semaphore.
                Defaults to 10.
            timeout: Soft total deadline in seconds for ``all()`` and
                iteration. On timeout, ``all()`` cancels outstanding pages
                and returns whatever completed (subject to
                ``return_exceptions``). ``None`` disables the deadline.
            return_exceptions: If True, failed/cancelled pages are skipped
                and successful items returned. If False (default), the first
                failure propagates.
            url_byte_budget: Max byte length of any comma-joined list-valued
                param. Lists exceeding this are split across requests; only
                one oversized list per query is supported.
        """
        self.client = client
        self.url = url
        self.page_model = page_model
        self.base_params = params or {}
        self.per_page = per_page
        self.page_param = page_param
        self.per_page_param = per_page_param
        self.start_page = start_page
        self.timeout = timeout
        self.return_exceptions = return_exceptions
        self.url_byte_budget = url_byte_budget
        self._sem = asyncio.Semaphore(max_concurrency)
        self._param_sets = self._split_long_params(self.base_params)

    def _split_long_params(self, params: dict) -> list[dict]:
        """Split list-valued params that would overflow the URL byte budget."""
        oversized = [
            k
            for k, v in params.items()
            if isinstance(v, list)
            and len(",".join(str(x) for x in v).encode("utf-8")) > self.url_byte_budget
        ]
        if not oversized:
            return [params]
        if len(oversized) > 1:
            raise ValueError(
                f"Cannot split more than one oversized list param: {oversized}"
            )
        key = oversized[0]
        values = params[key]
        chunk_size = len(values)
        while chunk_size > 1:
            joined = ",".join(str(x) for x in values[:chunk_size]).encode("utf-8")
            if len(joined) <= self.url_byte_budget:
                break
            chunk_size = max(1, int(chunk_size * 0.8))
        return [
            {**params, key: values[i : i + chunk_size]}
            for i in range(0, len(values), chunk_size)
        ]

    def _build_request_params(self, params: dict, page: int) -> dict:
        out = {
            k: ",".join(str(x) for x in v) if isinstance(v, list) else v
            for k, v in params.items()
        }
        out[self.page_param] = page
        out[self.per_page_param] = self.per_page
        return out

    async def _fetch(self, page: int, params: dict) -> list[Page[T]]:
        async with self._sem:
            resp = await self.client.get(
                self.url, params=self._build_request_params(params, page)
            )
            resp.raise_for_status()
            return [
                self.page_model.model_validate(r) for r in resp.json().get("data", {})
            ]

    async def all(self) -> list[T]:
        """Fetch all pages, returning a flat list in param-set + page order."""
        deadline = (
            asyncio.get_running_loop().time() + self.timeout
            if self.timeout is not None
            else None
        )

        def _remaining() -> float | None:
            if deadline is None:
                return None
            return max(0.0, deadline - asyncio.get_running_loop().time())

        # first page of each param set (needed for totals).
        first_tasks = [
            asyncio.create_task(self._fetch(self.start_page, params))
            for params in self._param_sets
        ]
        done, pending = await asyncio.wait(first_tasks, timeout=_remaining())
        for t in pending:
            t.cancel()

        firsts: list[Page[T] | None] = []
        for t in first_tasks:
            if t not in done:
                firsts.append(None)
                continue
            exc = t.exception()
            if exc is None:
                firsts.append(t.result())
            elif self.return_exceptions:
                firsts.append(None)
            else:
                raise exc
        # schedule remaining pages for successful firsts.
        rest_tasks: list[list[asyncio.Task]] = []
        for idx, first in enumerate(firsts):
            if first is None:
                rest_tasks.append([])
                continue
            n_pages = math.ceil(first.total / self.per_page) if self.per_page else 1
            params = self._param_sets[idx]
            rest_tasks.append(
                [
                    asyncio.create_task(self._fetch(p, params))
                    for p in range(self.start_page + 1, self.start_page + n_pages)
                ]
            )

        flat = [t for group in rest_tasks for t in group]
        if flat:
            _, pending2 = await asyncio.wait(flat, timeout=_remaining())
            for t in pending2:
                t.cancel()

        # assemble in order.
        out: list[T] = []
        for idx, first in enumerate(firsts):
            if first is None:
                continue
            out.extend(first.items)
            for t in rest_tasks[idx]:
                if not t.done() or t.cancelled():
                    continue
                exc = t.exception()
                if exc is not None:
                    if self.return_exceptions:
                        continue
                    raise exc
                out.extend(t.result().items)
        return out

    def __aiter__(self) -> AsyncIterator[T]:
        return self._iter_items()

    async def _iter_items(self) -> AsyncIterator[T]:
        """Stream items sequentially — lighter memory, preserves order.

        Terminates a param set on a partial page (more robust than relying
        on ``total`` alone, which may shift between requests).
        """
        async with asyncio.timeout(self.timeout):
            for params in self._param_sets:
                first = await self._fetch(self.start_page, params)
                for item in first.items:
                    yield item
                if len(first.items) < self.per_page:
                    continue
                total = first.total  # snapshot
                consumed = len(first.items)
                page_num = self.start_page + 1
                while consumed < total:
                    page = await self._fetch(page_num, params)
                    for item in page.items:
                        yield item
                    consumed += len(page.items)
                    if len(page.items) < self.per_page:
                        break
                    page_num += 1


async def paginate[T: BaseModel](
    client: httpx.AsyncClient,
    url: str,
    item_model: type[T],
    **kwargs,
) -> list[T]:
    """Convenience function for default pagination."""
    return await Paginator(client, url, _page_model_for(item_model), **kwargs).all()
