from __future__ import annotations

import inspect
from functools import wraps


def format_output(fn):
    """Formats output to be MPC compatible, if use_document_model is False."""

    def _format(self, result):
        if result is None or self.use_document_model:
            return result
        if isinstance(result, list):
            return [r.to_mpc() for r in result]
        return result.to_mpc()

    if inspect.iscoroutinefunction(fn):

        @wraps(fn)
        async def async_wrapper(self, *args, **kwargs):
            result = await fn(self, *args, **kwargs)
            return _format(self, result)

        return async_wrapper

    @wraps(fn)
    def sync_wrapper(self, *args, **kwargs):
        result = fn(self, *args, **kwargs)
        return _format(self, result)

    return sync_wrapper
