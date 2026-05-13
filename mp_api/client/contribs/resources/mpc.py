from __future__ import annotations

from functools import wraps


def format_output(fn):
    """Wraps a function and determines output format of model."""

    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        result = fn(self, *args, **kwargs)
        if result is None or self.use_document_model:
            return result
        if isinstance(result, list):
            return [r.to_mpc() for r in result]
        return result.to_mpc()

    return wrapper
