"""Define core client functionality."""

from __future__ import annotations

import functools
import importlib.metadata
import itertools
import logging
import sys
import time
import warnings
from base64 import urlsafe_b64encode
from concurrent.futures import as_completed
from enum import StrEnum
from pathlib import Path
from tempfile import gettempdir
from typing import TYPE_CHECKING, Literal, Mapping
from urllib.parse import urlsplit

import orjson
import pandas as pd
import plotly.io as pio
import requests
from bravado.config import bravado_config_from_config_dict
from bravado.requests_client import RequestsClient
from bravado.swagger_model import Loader
from bravado_core.formatter import SwaggerFormat
from bravado_core.model import model_discovery
from bravado_core.resource import build_resources
from bravado_core.spec import Spec, _identity, build_api_serving_url
from cachetools import LRUCache, cached  # type: ignore[import-untyped]
from cachetools.keys import hashkey  # type: ignore[import-untyped]
from pyisemail import is_email
from pyisemail.diagnosis import BaseDiagnosis
from requests.exceptions import RequestException
from requests_futures.sessions import FuturesSession
from swagger_spec_validator.common import SwaggerValidationError
from tqdm.auto import tqdm
from urllib3.util.retry import Retry

from mp_api.client.contribs._logger import MPCC_LOGGER, TqdmToLogger
from mp_api.client.contribs.settings import MPCC_SETTINGS
from mp_api.client.core.exceptions import MPContribsClientError
from mp_api.client.core.schemas import _DictLikeAccess

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Sequence
    from typing import Any


class VALID_OPS(StrEnum):
    QUERY = "query"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    DOWNLOAD = "download"


VALID_OPS_T = Literal[*VALID_OPS]  # type: ignore[valid-type]


def timeit(func):
    """Decorator for functions that want to log timing info."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            arg_repr = ", ".join(
                [repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()]
            )
            MPCC_LOGGER.info("%s(%s) took %.4fs", func.__name__, arg_repr, elapsed)

    return wrapper


def prune_dict(
    payload: dict[str, Any],
    disallowed_keys: list[str] | None = None,
    required_keys: list[str] | None = None,
    reference: _DictLikeAccess | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Method to clean dictionaries of disallowed keys with standardized logging.

    Args:
        payload (dict[str, Any]): the dict to clean
        disallowed_keys (list[str]): the keys to remove from payload
        required_keys (list[str]): fields to keepy (if None or [] all payload keys are kept)
        reference (_DictLikeAccess | dict[str, Any]): a reference object to validate payload key-values against
    """
    if disallowed_keys:
        for k in list(payload.keys()):
            if k in disallowed_keys:
                MPCC_LOGGER.warning(f"removing `{k}` from update - not allowed.")
                payload.pop(k)
                if k == "columns":
                    MPCC_LOGGER.info(
                        "use `client.init_columns()` to update project columns."
                    )
                elif k == "is_public":
                    MPCC_LOGGER.info(
                        "use `client.make_public/private()` to set `is_public`."
                    )
            elif not isinstance(payload[k], bool) and not payload[k]:
                MPCC_LOGGER.warning(
                    f"removing `{k}` from update - no update requested."
                )
                payload.pop(k)

    if required_keys:
        payload = {k: v for k, v in payload.items() if k in required_keys}

    if reference:
        payload = {k: v for k, v in payload.items() if reference.get(k, None) != v}

    if not payload:
        MPCC_LOGGER.warning("nothing to update")

    return payload


pd.options.plotting.backend = "plotly"
pio.templates.default = "simple_white"
warnings.formatwarning = lambda msg, *args, **kwargs: f"{msg}\n"
warnings.filterwarnings("default", category=DeprecationWarning, module=__name__)


def validate_email(email_string: str) -> None:
    """Validate user email address.

    Args:
        email_string (str) : the user's email address
    Returns:
        None
    Raises:
        SwaggerValidationError on malformed email address.
    """
    if email_string.count(":") != 1:
        raise SwaggerValidationError(
            f"{email_string} not of format <provider>:<email>."
        )

    provider, email = email_string.split(":", 1)
    if provider not in MPCC_SETTINGS.PROVIDERS:
        raise SwaggerValidationError(f"{provider} is not a valid provider.")

    d = is_email(email, diagnose=True)
    if d > BaseDiagnosis.CATEGORIES["VALID"]:
        raise SwaggerValidationError(f"{email} {d.message}")

    return None


# TODO: mypy has some problems with putting a bare `str`
# as a callable function in SwaggerFormat
email_format = SwaggerFormat(
    format="email",
    to_wire=str,  # type: ignore[arg-type]
    to_python=str,  # type: ignore[arg-type]
    validate=validate_email,
    description="e-mail address including provider",
)


def validate_url(
    url_string: str, qualifying: Sequence[str] = ("scheme", "netloc")
) -> None:
    """Verify an endpoint URL.

    Args:
        url_string (str) : the URL as a string
        qualifying (Sequence of str) : attributes to check for instantiation on the URL

    Returns:
        None

    Raises:
        SwaggerValidationError if any `qualifying` fields are missing

    """
    tokens = urlsplit(url_string)
    if not all(getattr(tokens, qual_attr) for qual_attr in qualifying):
        raise SwaggerValidationError(f"{url_string} invalid")


url_format = SwaggerFormat(
    format="url",
    to_wire=str,  # type: ignore[arg-type]
    to_python=str,  # type: ignore[arg-type]
    validate=validate_url,
    description="URL",
)
bravado_config_dict = {
    "validate_responses": False,
    "use_models": False,
    "include_missing_properties": False,
    "formats": [email_format, url_format],
}
bravado_config = bravado_config_from_config_dict(bravado_config_dict)
for key in set(bravado_config._fields).intersection(set(bravado_config_dict)):
    del bravado_config_dict[key]
bravado_config_dict["bravado"] = bravado_config


# https://stackoverflow.com/a/8991553
def grouper(n: int, iterable: Iterable) -> Generator:
    """Collect data into non-overlapping fixed-length chunks or blocks.

    Args:
        n (int) : Maximum number of elements per block
        iterable (Iterable) : object to divide into blocks

    Returns:
        Generator of input iterable divided into blocks
    """
    it = iter(iterable)
    while True:
        chunk = tuple(itertools.islice(it, n))
        if not chunk:
            return
        yield chunk


def get_session(session: requests.Session | None = None) -> FuturesSession:
    """Start a futures session.

    Args:
        session (requests.Session or None) : Optional Session to use
            in starting a FuturesSession
    Returns:
        FuturesSession
    """
    adapter_kwargs = dict(
        max_retries=Retry(
            total=MPCC_SETTINGS.RETRIES,
            read=MPCC_SETTINGS.RETRIES,
            connect=MPCC_SETTINGS.RETRIES,
            respect_retry_after_header=True,
            status_forcelist=[429, 502],  # rate limit
            allowed_methods={"DELETE", "GET", "PUT", "POST"},
            backoff_factor=2,
        )
    )
    return FuturesSession(
        session=session if session else requests.Session(),
        max_workers=MPCC_SETTINGS.MAX_WORKERS,
        adapter_kwargs=adapter_kwargs,
    )


def _response_hook(resp, *args, **kwargs):
    content_type = resp.headers["content-type"]
    if content_type == "application/json":
        result = resp.json()

        if isinstance(result, dict):
            if "data" in result and isinstance(result["data"], list):
                resp.result = result
                resp.count = len(result["data"])
            elif "count" in result and isinstance(result["count"], int):
                resp.count = result["count"]

            if "warning" in result:
                MPCC_LOGGER.warning(result["warning"])
            elif "error" in result and isinstance(result["error"], str):
                MPCC_LOGGER.error(result["error"][:10000] + "...")
        elif isinstance(result, list):
            resp.result = result
            resp.count = len(result)

    elif content_type == "application/gzip":
        resp.result = resp.content
        resp.count = 1
    else:
        MPCC_LOGGER.error(f"request failed with status {resp.status_code}!")
        resp.count = 0


def _run_futures(
    futures, total: int = 0, timeout: int = -1, desc=None, disable=False
) -> dict[str, dict[str, Any]]:
    """Helper to run futures/requests."""
    start = time.perf_counter()
    total_set = total > 0
    total = total if total_set else len(futures)
    responses: dict[str, dict[str, Any]] = {}

    with tqdm(  # type: ignore[call-arg,attr-defined]
        total=total,
        desc=desc,
        file=TqdmToLogger(),
        miniters=1,
        delay=5,
        disable=disable,
    ) as pbar:
        for future in as_completed(futures):
            if not future.cancelled():
                response = future.result()
                cnt = response.count if total_set and hasattr(response, "count") else 1
                pbar.update(cnt)

                if hasattr(future, "track_id"):
                    tid = future.track_id
                    responses[tid] = {}
                    if hasattr(response, "result"):
                        responses[tid]["result"] = response.result
                    if hasattr(response, "count"):
                        responses[tid]["count"] = response.count

                elapsed = time.perf_counter() - start
                timed_out = timeout > 0 and elapsed > timeout

                if timed_out:
                    for fut in futures:
                        fut.cancel()

    return responses


@functools.lru_cache(maxsize=1000)
def _load(protocol, host, headers_json, project, version):
    spec_dict = _raw_specs(protocol, host, version)
    headers = orjson.loads(headers_json)

    if not spec_dict["paths"]:
        url = f"{protocol}://{host}"
        origin_url = f"{url}/apispec.json"
        http_client = RequestsClient()
        http_client.session.headers.update(headers)
        swagger_spec = Spec.from_dict(
            spec_dict, origin_url, http_client, bravado_config_dict
        )
        http_client.session.close()
        return swagger_spec

    # retrieve list of projects accessible to user
    query = {"name": project} if project else {}
    query["_fields"] = ["name"]
    url = f"{protocol}://{host}"
    resp = requests.get(f"{url}/projects/", params=query, headers=headers).json()

    if not resp or not resp["data"]:
        raise MPContribsClientError(f"Failed to load projects for query {query}!")

    if project and not resp["data"]:
        raise MPContribsClientError(f"{project} doesn't exist, or access denied!")

    projects = sorted(d["name"] for d in resp["data"])
    # expand regex-based query parameters for `data` columns
    spec = _expand_params(
        protocol,
        host,
        version,
        orjson.dumps(projects),
        api_key=headers.get("x-api-key"),
    )
    spec.http_client.session.headers.update(headers)
    return spec


@functools.lru_cache(maxsize=1)
def _raw_specs(protocol, host, version):
    http_client = RequestsClient()
    url = f"{protocol}://{host}"
    origin_url = f"{url}/apispec.json"
    url4fn = origin_url.replace("apispec", f"apispec-{version}").encode("utf-8")
    fn = urlsafe_b64encode(url4fn).decode("utf-8")
    apispec = Path(gettempdir()) / fn
    spec_dict = None

    if apispec.exists():
        spec_dict = orjson.loads(apispec.read_bytes())
        MPCC_LOGGER.debug(
            f"Specs for {origin_url} and {version} re-loaded from {apispec}."
        )
    else:
        loader = Loader(http_client)
        spec_dict = loader.load_spec(origin_url)

        with apispec.open("wb") as f:
            f.write(orjson.dumps(spec_dict))

        MPCC_LOGGER.debug(f"Specs for {origin_url} and {version} saved as {apispec}.")

    if not spec_dict:
        raise MPContribsClientError(
            f"Couldn't load specs from {url} for {version}!"
        )  # not cached

    spec_dict["host"] = host
    spec_dict["schemes"] = [protocol]
    http_client.session.close()
    return spec_dict


@cached(
    cache=LRUCache(maxsize=100),
    key=lambda protocol, host, version, projects_json, **kwargs: hashkey(
        protocol, host, version, projects_json
    ),
)
def _expand_params(protocol, host, version, projects_json, api_key=None):
    columns = {"string": [], "number": []}
    projects = orjson.loads(projects_json)
    query = {"project__in": ",".join(projects)}
    query["_fields"] = "columns"
    url = f"{protocol}://{host}"
    http_client = RequestsClient()
    http_client.session.headers["Content-Type"] = "application/json"
    if api_key:
        http_client.session.headers["X-Api-Key"] = api_key
    resp = http_client.session.get(f"{url}/projects/", params=query).json()

    for proj in resp["data"]:
        for column in proj["columns"]:
            if column["path"].startswith("data."):
                col = column["path"].replace(".", "__")
                if column["unit"] == "NaN":
                    columns["string"].append(col)
                else:
                    col = f"{col}__value"
                    columns["number"].append(col)

    spec_dict = _raw_specs(protocol, host, version)
    resource = spec_dict["paths"]["/contributions/"]["get"]
    raw_params = resource.pop("parameters")
    params = {}

    for param in raw_params:
        if param["name"].startswith("^data__"):
            op = param["name"].rsplit("$__", 1)[-1]
            typ = param["type"]
            key = "number" if typ == "number" else "string"

            for column in columns[key]:
                param_name = f"{column}__{op}"
                if param_name not in params:
                    param_spec = {
                        k: v
                        for k, v in param.items()
                        if k not in ["name", "description"]
                    }
                    param_spec["name"] = param_name
                    params[param_name] = param_spec
        else:
            params[param["name"]] = param

    resource["parameters"] = list(params.values())

    origin_url = f"{url}/apispec.json"
    spec = Spec(spec_dict, origin_url, http_client, bravado_config_dict)
    model_discovery(spec)

    if spec.config["internally_dereference_refs"]:
        spec.deref = _identity
        spec._internal_spec_dict = spec.deref_flattened_spec

    for user_defined_format in spec.config["formats"]:
        spec.register_format(user_defined_format)

    spec.resources = build_resources(spec)
    spec.api_url = build_api_serving_url(
        spec_dict=spec.spec_dict,
        origin_url=spec.origin_url,
        use_spec_url_for_base_path=spec.config["use_spec_url_for_base_path"],
    )
    http_client.session.close()
    return spec


@functools.lru_cache(maxsize=1)
def _version(url):
    retries, max_retries = 0, 3
    protocol = urlsplit(url).scheme
    if "pytest" in sys.modules and protocol == "http":
        return importlib.metadata.version("mp-api")

    while retries < max_retries:
        try:
            r = requests.get(f"{url}/healthcheck", timeout=5)
            if r.status_code in {200, 403}:
                return r.json().get("version")
            else:
                retries += 1
                MPCC_LOGGER.warning(
                    f"Healthcheck for {url} failed ({r.status_code})! Wait 30s."
                )
                time.sleep(30)
        except RequestException as ex:
            retries += 1
            MPCC_LOGGER.warning(f"Could not connect to {url} ({ex})! Wait 30s.")
            time.sleep(30)
