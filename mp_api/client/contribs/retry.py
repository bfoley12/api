from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import wraps
from typing import Any, ParamSpec, TypeVar, overload

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Brendan TODO: put into settigns
RETRYABLE_STATUSES = frozenset({429, 502})


def _parse_retry_after(value: str) -> float | None:
    """Retry-After is either delta-seconds or an HTTP-date (RFC 7231 §7.1.3)."""
    value = value.strip()
    # Try delta-seconds first
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    # Fall back to HTTP-date
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_at is None:
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    delta = (retry_at - datetime.now(UTC)).total_seconds()
    return max(0.0, delta)


class wait_retry_after_or_exponential:
    """Honor Retry-After header if present, else exponential backoff."""

    def __init__(self, *, multiplier: float, min: float, max: float):
        """Honor Retry-After header if present, else exponential backoff."""
        self._fallback = wait_exponential(multiplier=multiplier, min=min, max=max)
        self._max = max

    def __call__(self, retry_state: RetryCallState) -> float:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        if isinstance(exc, httpx.HTTPStatusError):
            header = exc.response.headers.get("Retry-After")
            if header:
                parsed = _parse_retry_after(header)
                if parsed is not None:
                    return min(parsed, self._max)
        return self._fallback(retry_state)


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

    def _is_retryable_exc(exc: BaseException) -> bool:
        return (
            isinstance(exc, httpx.HTTPStatusError)
            and exc.response.status_code in statuses
        )

    decorator = retry(
        stop=stop_after_attempt(attempts),
        wait=wait_retry_after_or_exponential(
            multiplier=backoff_multiplier,
            min=backoff_multiplier,
            max=backoff_max,
        ),
        retry=(
            retry_if_exception_type(httpx.TransportError)
            | retry_if_exception(_is_retryable_exc)
        ),
        reraise=True,
    )
    if func is None:
        return decorator  # used as @standard_retry(...)
    return decorator(func)  # used as @standard_retry


P = ParamSpec("P")
R = TypeVar("R")


@overload
def standard_timeout[**P, R](
    func: Callable[P, Awaitable[R]], /
) -> Callable[P, Awaitable[R]]: ...
@overload
def standard_timeout[**P, R](
    *,
    seconds: float | None = ...,
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
