import json
from typing import Any, Optional
from langchain_core.tools import tool
import requests

# These are set per-request before agent invocation
_base_url: str = ""
_session_token: str = ""


def set_credentials(base_url: str, session_token: str):
    global _base_url, _session_token
    _base_url = base_url
    _session_token = session_token


def _auth():
    return ("0", _session_token)


@tool
def tripletex_get(endpoint: str, params: Optional[dict] = None) -> str:
    """Make a GET request to the Tripletex API.

    Args:
        endpoint: API path, e.g. "/employee" or "/customer"
        params: Optional query parameters, e.g. {"fields": "id,firstName,lastName", "count": 100}

    Returns:
        JSON response as a string
    """
    url = f"{_base_url}{endpoint}"
    resp = requests.get(url, auth=_auth(), params=params or {})
    return resp.text


@tool
def tripletex_post(endpoint: str, body: dict) -> str:
    """Make a POST request to the Tripletex API to create a resource.

    Args:
        endpoint: API path, e.g. "/employee" or "/customer"
        body: JSON body as a dict

    Returns:
        JSON response as a string
    """
    url = f"{_base_url}{endpoint}"
    resp = requests.post(url, auth=_auth(), json=body)
    return resp.text


@tool
def tripletex_put(endpoint: str, body: dict) -> str:
    """Make a PUT request to the Tripletex API to update a resource.

    Args:
        endpoint: API path including ID, e.g. "/employee/123"
        body: JSON body as a dict with updated fields

    Returns:
        JSON response as a string
    """
    url = f"{_base_url}{endpoint}"
    resp = requests.put(url, auth=_auth(), json=body)
    return resp.text


@tool
def tripletex_delete(endpoint: str) -> str:
    """Make a DELETE request to the Tripletex API.

    Args:
        endpoint: API path including ID, e.g. "/employee/123"

    Returns:
        HTTP status code and response text
    """
    url = f"{_base_url}{endpoint}"
    resp = requests.delete(url, auth=_auth())
    return f"Status: {resp.status_code}\n{resp.text}"


ALL_TOOLS = [tripletex_get, tripletex_post, tripletex_put, tripletex_delete]
