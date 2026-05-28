from __future__ import annotations

from typing import TYPE_CHECKING, Self

import httpx
import orjson

from mp_api.client.contribs import helpers
from mp_api.client.contribs._logger import MPCC_LOGGER
from mp_api.client.contribs.settings import MPCC_SETTINGS
from mp_api.client.core.exceptions import MPContribsClientError

if TYPE_CHECKING:
    from typing import Any


def handle_api_key(
    api_key: str | None, headers: dict[str, Any] | None, **kwargs
) -> tuple[str | None, dict[str, Any]]:
    """Checks kwargs for api key and corrects outdated formats.
    Throws error if api key is invalid.

    Args:
        api_key (str): user provided api_key
        headers: dict[str, Any]: custom headers for localhost connection
        **kwargs (dict[str, Any]): kwargs possibly containing the api key

    Returns:
        tuple: (validated api key, remaining kwargs after popping api_key)
    """
    if "apikey" in kwargs:
        api_key_warn = (
            "`apikey` has been deprecated in favor of `api_key` for "
            " consistency with the Materials Project API client."
        )
        if api_key:
            api_key_warn += (
                " Ignoring `apikey` in favor of `api_key`, which was also set."
            )
        else:
            api_key = kwargs.pop("apikey")
        MPCC_LOGGER.warning(api_key_warn)

    if api_key and len(api_key) != 32:
        raise MPContribsClientError(f"Invalid API key: {api_key}")

    if api_key and headers:
        api_key = None
        MPCC_LOGGER.debug("headers set => ignoring apikey!")

    if not api_key and not headers:
        raise MPContribsClientError("Must specify either api_key or headers!")

    return api_key, kwargs


class BaseClient:
    """client to connect to MPContribs API.

    Typical usage:
        - set environment variable MPCONTRIBS_API_KEY to the API key from your MP profile
        - import and init:
            >>> from mp_api.client.contribs.client import ContribsClient
            >>> client = ContribsClient()
    """

    def __init__(
        self,
        api_key: str | None = MPCC_SETTINGS.API_KEY,
        headers: dict[str, Any] | None = None,
        host: str | None = None,
        http: httpx.Client | None = None,
        **kwargs,
    ) -> None:
        """Initialize the client - only reloads API spec from server as needed.

        Args:
            api_key (str): API key (or use MPCONTRIBS_API_KEY env var) - ignored if headers set
            headers (dict): custom headers for localhost connections
            host (str): host address to connect to (or use MPCONTRIBS_API_HOST env var)
            http (httpx.Client): override the httpx client to use
            kwargs : To handle deprecated class attributes
        """
        # - Kong forwards consumer headers when api-key used for auth
        # - forward consumer headers when connecting through localhost

        api_key, kwargs = handle_api_key(api_key, headers, **kwargs)

        # Brendan TODO: Could go even further and define a Transport class for some (or all) fields. Probably too much indirection though
        self.api_key = api_key
        self.headers = headers or {}
        self.headers["x-api-key"] = api_key if api_key else None
        self.headers["Content-Type"] = "application/json"
        if http is not None and self.headers:
            http.headers.update(**self.headers)
        self.headers_json = orjson.dumps(
            {k: self.headers[k] for k in sorted(self.headers)}
        )
        self.host = host or MPCC_SETTINGS.API_HOST
        ssl = self.host.endswith(".materialsproject.org") and not self.host.startswith(
            "localhost."
        )
        self.protocol = "https" if ssl else "http"
        if not self.host.startswith("http://") and not self.host.startswith("https://"):
            self.url = f"{self.protocol}://{self.host}"

        if self.url not in MPCC_SETTINGS.VALID_URLS:
            raise MPContribsClientError(
                f"{self.url} not a valid URL (one of "
                f"{', '.join(MPCC_SETTINGS.VALID_URLS)})"
            )
        self._http = (
            http
            if http is not None
            else httpx.Client(base_url=self.url, headers=self.headers)
        )
        self.version = helpers._version(self.url)  # includes healthcheck

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def apikey(self) -> str | None:
        """Handle deprecated `apikey` attr."""
        MPCC_LOGGER.warning(
            "`apikey` has been deprecated in favor of `api_key` for "
            " consistency with the Materials Project API client."
        )
        return self.api_key


class AsyncBaseClient:
    """client to connect to MPContribs API.

    Typical usage:
        - set environment variable MPCONTRIBS_API_KEY to the API key from your MP profile
        - import and init:
          >>> from mp_api.client.contribs.client import ContribsClient
          >>> client = ContribsClient()
    """

    def __init__(
        self,
        api_key: str | None = MPCC_SETTINGS.API_KEY,
        headers: dict | None = None,
        host: str | None = None,
        http: httpx.AsyncClient | None = None,
        **kwargs,
    ) -> None:
        """Initialize the client - only reloads API spec from server as needed.

        Args:
            api_key (str): API key (or use MPCONTRIBS_API_KEY env var) - ignored if headers set
            headers (dict): custom headers for localhost connections
            host (str): host address to connect to (or use MPCONTRIBS_API_HOST env var)
            http (httpx.Client): override the httpx client to use
            kwargs : To handle deprecated class attributes
        """
        # - Kong forwards consumer headers when api-key used for auth
        # - forward consumer headers when connecting through localhost

        api_key, kwargs = handle_api_key(api_key, headers, **kwargs)

        # Brendan TODO: Could go even further and define a Transport class for some (or all) fields. Probably too much indirection though
        self.api_key = api_key
        self.headers = headers or {}
        self.headers = {"x-api-key": api_key} if api_key else self.headers
        self.headers["Content-Type"] = "application/json"
        self.headers_json = orjson.dumps(
            {k: self.headers[k] for k in sorted(self.headers)}
        )
        self.host = host or MPCC_SETTINGS.API_HOST
        ssl = self.host.endswith(".materialsproject.org") and not self.host.startswith(
            "localhost."
        )
        self.protocol = "https" if ssl else "http"
        self.url = f"{self.protocol}://{self.host}"

        if self.url not in MPCC_SETTINGS.VALID_URLS:
            raise MPContribsClientError(
                f"{self.url} not a valid URL (one of "
                f"{', '.join(MPCC_SETTINGS.VALID_URLS)})"
            )

        self._http = (
            http
            if http is not None
            else httpx.AsyncClient(base_url=self.url, headers=headers)
        )
        self.version = helpers._version(self.url)  # includes healthcheck

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    @property
    def apikey(self) -> str | None:
        """Handle deprecated `apikey` attr."""
        MPCC_LOGGER.warning(
            "`apikey` has been deprecated in favor of `api_key` for "
            " consistency with the Materials Project API client."
        )
        return self.api_key
