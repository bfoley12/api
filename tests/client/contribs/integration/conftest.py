from typing import Iterator

import httpx
import os
import pytest

from mp_api.client.contribs.client import ContribsClient


@pytest.fixture(scope="session")
def api_key() -> str:
    key = os.environ.get("MPCONTRIBS_API_KEY")
    if not key:
        pytest.skip("MPCONTRIBS_API_KEY not set", allow_module_level=True)
    return key


@pytest.fixture(scope="session")
def api_base_url():
    url = "localhost.contribs-api.materialsproject.org"
    try:
        httpx.get(f"http://{url}/healthcheck", timeout=2.0).raise_for_status()
    except (httpx.HTTPError, httpx.ConnectError):
        pytest.skip(
            "Dev API not running at localhost.contribs-api.materialsproject.org",
            allow_module_level=True,
        )
    return url


@pytest.fixture
def client(api_base_url, api_key) -> Iterator[ContribsClient]:
    with ContribsClient(
        host=api_base_url, use_document_model=True, api_key=api_key
    ) as c:
        yield c
