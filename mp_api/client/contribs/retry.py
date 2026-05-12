from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, overload

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

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
