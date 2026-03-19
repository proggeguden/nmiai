import time
from typing import Optional

import requests
from langchain_core.tools import tool

from logger import get_logger

log = get_logger("tripletex.api")

# Set per-request before agent invocation
_base_url: str = ""
_session_token: str = ""

# Counters reset per request
_call_count: int = 0
_error_count: int = 0


def set_credentials(base_url: str, session_token: str) -> None:
    global _base_url, _session_token, _call_count, _error_count
    _base_url = base_url
    _session_token = session_token
    _call_count = 0
    _error_count = 0


def get_stats() -> dict:
    return {"api_calls": _call_count, "api_errors": _error_count}


def _auth():
    return ("0", _session_token)


def _make_request(method: str, endpoint: str, params: dict = None, body: dict = None) -> str:
    global _call_count, _error_count

    url = f"{_base_url}{endpoint}"
    _call_count += 1

    log.info(
        f"→ {method} {endpoint}",
        method=method,
        endpoint=endpoint,
        params=params or {},
        body=body,
        call_num=_call_count,
    )

    t0 = time.monotonic()
    try:
        if method == "GET":
            resp = requests.get(url, auth=_auth(), params=params or {})
        elif method == "POST":
            resp = requests.post(url, auth=_auth(), json=body)
        elif method == "PUT":
            resp = requests.put(url, auth=_auth(), json=body)
        elif method == "DELETE":
            resp = requests.delete(url, auth=_auth())
        else:
            raise ValueError(f"Unknown method: {method}")
    except Exception as e:
        elapsed = time.monotonic() - t0
        log.error(f"✗ {method} {endpoint} — network error", error=str(e), elapsed_ms=round(elapsed * 1000))
        raise

    elapsed_ms = round((time.monotonic() - t0) * 1000)
    status = resp.status_code
    is_error = status >= 400

    if is_error:
        _error_count += 1
        log.warning(
            f"✗ {method} {endpoint} → {status} (4xx/5xx — hurts efficiency score!)",
            method=method,
            endpoint=endpoint,
            status=status,
            elapsed_ms=elapsed_ms,
            response=resp.text[:2000],  # cap to avoid log spam
        )
    else:
        log.info(
            f"✓ {method} {endpoint} → {status}",
            method=method,
            endpoint=endpoint,
            status=status,
            elapsed_ms=elapsed_ms,
            response=resp.text[:2000],
        )

    return resp.text


@tool
def tripletex_get(endpoint: str, params: Optional[dict] = None) -> str:
    """Make a GET request to the Tripletex API.

    Args:
        endpoint: API path, e.g. "/employee" or "/customer"
        params: Optional query parameters, e.g. {"fields": "id,firstName,lastName", "count": 100}

    Returns:
        JSON response as a string
    """
    return _make_request("GET", endpoint, params=params)


@tool
def tripletex_post(endpoint: str, body: dict) -> str:
    """Make a POST request to the Tripletex API to create a resource.

    Args:
        endpoint: API path, e.g. "/employee" or "/customer"
        body: JSON body as a dict

    Returns:
        JSON response as a string
    """
    return _make_request("POST", endpoint, body=body)


@tool
def tripletex_put(endpoint: str, body: dict) -> str:
    """Make a PUT request to the Tripletex API to update a resource.

    Args:
        endpoint: API path including ID, e.g. "/employee/123"
        body: JSON body as a dict with updated fields

    Returns:
        JSON response as a string
    """
    return _make_request("PUT", endpoint, body=body)


@tool
def tripletex_delete(endpoint: str) -> str:
    """Make a DELETE request to the Tripletex API.

    Args:
        endpoint: API path including ID, e.g. "/employee/123"

    Returns:
        HTTP status code and response text
    """
    return _make_request("DELETE", endpoint)


ALL_TOOLS = [tripletex_get, tripletex_post, tripletex_put, tripletex_delete]
