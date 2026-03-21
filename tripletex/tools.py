"""Tripletex API tools — credentials, request helpers, and tool loading."""

import os
import time

import requests

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
            resp = requests.post(url, auth=_auth(), json=body, params=params or {})
        elif method == "PUT":
            resp = requests.put(url, auth=_auth(), json=body, params=params or {})
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
            response=resp.text[:2000],
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


def load_tools(swagger_path: str = None):
    """Load tools — generic (default) or legacy typed tools.

    Returns:
        Tuple of (tools_list, tool_summaries_str)
    """
    use_generic = os.environ.get("USE_GENERIC_TOOLS", "true").lower() != "false"

    if use_generic:
        from generic_tools import build_generic_tools, get_tier1_catalog
        tools = build_generic_tools(_make_request)
        summaries = get_tier1_catalog()
        log.info(f"Loaded {len(tools)} generic tools (call_api + lookup_endpoint + analyze_response)")
        return tools, summaries
    else:
        # Legacy: typed tools from swagger
        from swagger_tools import generate_tools, get_tool_summaries
        if swagger_path is None:
            swagger_path = os.path.join(os.path.dirname(__file__), "swagger.json")
        tools = generate_tools(swagger_path, _make_request)
        summaries = get_tool_summaries(tools)
        log.info(f"Loaded {len(tools)} legacy typed tools from swagger.json")
        return tools, summaries
