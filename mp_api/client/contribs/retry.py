from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Awaitable, ParamSpec, overload, TypeVar
from functools import wraps
import asyncio

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

# Brendan TODO: put into settigns
RETRYABLE_STATUSES = frozenset({429, 502})


@overload
def standard_retry(func: Callable[..., Any], /) -> Callable[..., Any]: ...


@overload
def standard_retry(
    *,
    attempts: int = 5,
    backoff_multiplier: float = 0.5,
    backoff_max: float = 10.0,
    retryable_statuses: Iterable[int] = RETRYABLE_STATUSES,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


# Brendan TODO: Use settings
def standard_retry(
    func=None,
    /,
    *,
    attempts=5,
    backoff_multiplier=0.5,
    backoff_max=10.0,
    retryable_statuses: Iterable[int] = RETRYABLE_STATUSES,
):
    """Defines a retry policy to use on http methods.
    Can be cusotmized by supplying arguments or used as default.
    """
    statuses = frozenset(retryable_statuses)

    def _is_retryable(response: httpx.Response) -> bool:
        return response.status_code in statuses

    decorator = retry(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(
            multiplier=backoff_multiplier, min=backoff_multiplier, max=backoff_max
        ),
        retry=(
            retry_if_exception_type(httpx.TransportError)
            | retry_if_result(_is_retryable)
        ),
        reraise=True,
    )
    if func is None:
        return decorator  # used as @standard_retry(...)
    return decorator(func)  # used as @standard_retry


P = ParamSpec("P")
R = TypeVar("R")


@overload
def standard_timeout[**P, R](func: Callable[P, Awaitable[R]], /) -> Callable[P, Awaitable[R]]: ...
@overload
def standard_timeout[**P, R](
    *, seconds: float | None = ...,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]: ...

def standard_timeout(
    func: Callable[..., Awaitable[Any]] | None = None,
    /,
    *,
    seconds: float | None = 5.0,
) -> Any:
    """Provides a guaranteed function timeout."""
    def decorator(f: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(f)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async with asyncio.timeout(seconds):
                return await f(*args, **kwargs)
        return wrapper
    return decorator if func is None else decorator(func)
