from __future__ import annotations

import httpx


class APIError(Exception):
    def __init__(self, response: httpx.Response):
        """Init for APIError."""
        self.response = response
        self.status_code = response.status_code
        try:
            self.detail = response.json()
        except ValueError:
            self.detail = response.text
        super().__init__(
            f"[{self.status_code}] {response.request.method} "
            f"{response.request.url}\n{self.detail}"
        )


def check_response(response: httpx.Response) -> None:
    """Event hook for httpx.Clients to automatically return errors from apis as an APIError.

    Args:
        response (httpx.Response): the response from an httpx.request

    Raises:
        APIError: if response is an error
    """
    if response.is_error:
        response.read()
        raise APIError(response)
