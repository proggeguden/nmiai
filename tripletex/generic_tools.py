"""Generic Tripletex API tools — call_api + lookup_endpoint."""

import json
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from endpoint_catalog import FULL_CATALOG, TIER1_CATALOG, ENDPOINT_SCHEMAS


class CallApiArgs(BaseModel):
    method: str = Field(description="HTTP method: GET, POST, PUT, or DELETE")
    path: str = Field(description="API path with IDs substituted, e.g. /customer/123")
    query_params: Optional[dict] = Field(default=None, description="Query parameters as dict")
    body: Optional[dict | list] = Field(default=None, description="Request body (camelCase). Dict for single, list for bulk /list endpoints.")


class LookupEndpointArgs(BaseModel):
    query: str = Field(description="Search keywords, e.g. 'supplier', 'payment type', 'voucher posting'")


def build_generic_tools(make_request_fn):
    """Build the two generic tools.

    Args:
        make_request_fn: The _make_request function from tools.py

    Returns:
        List of [call_api, lookup_endpoint] StructuredTools
    """

    def call_api(method: str, path: str, query_params: dict = None, body: dict | list = None) -> str:
        """Call any Tripletex API endpoint. Use the API reference in the prompt to construct correct requests."""
        method = method.upper()
        if method not in ("GET", "POST", "PUT", "DELETE"):
            return json.dumps({"status": 400, "message": f"Invalid method: {method}. Use GET, POST, PUT, or DELETE."})
        return make_request_fn(method, path, params=query_params, body=body)

    def lookup_endpoint(query: str) -> str:
        """Search the full API catalog for endpoints matching the query. Returns endpoint docs with schemas."""
        query_lower = query.lower()
        keywords = query_lower.split()

        results = []

        # First: match on section tag name (the ### header line)
        for section in FULL_CATALOG.split("\n### "):
            if not section.strip():
                continue
            # The tag is the first line of the section
            tag_line = section.split("\n")[0].lower()
            if all(kw in tag_line for kw in keywords):
                results.append("### " + section.strip())

        # Second: match on endpoint lines (METHOD /path — description)
        if not results:
            for section in FULL_CATALOG.split("\n### "):
                if not section.strip():
                    continue
                lines = section.split("\n")
                tag = lines[0].strip()
                for line in lines[1:]:
                    stripped = line.strip()
                    if stripped and (stripped.startswith("GET ") or stripped.startswith("POST ") or
                                     stripped.startswith("PUT ") or stripped.startswith("DELETE ")):
                        if any(kw in stripped.lower() for kw in keywords):
                            # Include the endpoint + its following detail lines
                            idx = lines.index(line)
                            block = [f"[{tag}] {stripped}"]
                            for detail_line in lines[idx+1:]:
                                if detail_line.startswith("  "):
                                    block.append(detail_line)
                                else:
                                    break
                            results.append("\n".join(block))

        if not results:
            return "No matching endpoints found. Try broader keywords."

        return "\n".join(results[:20])  # Cap at 20 results

    call_api_tool = StructuredTool.from_function(
        func=call_api,
        name="call_api",
        description="Call any Tripletex API endpoint. method: GET/POST/PUT/DELETE. path: API path with IDs (e.g. /customer/123). query_params: dict of query params. body: request body in camelCase.",
        args_schema=CallApiArgs,
    )

    lookup_tool = StructuredTool.from_function(
        func=lookup_endpoint,
        name="lookup_endpoint",
        description="Search the API documentation for endpoints by keyword. Use when you need an endpoint not listed in the main reference.",
        args_schema=LookupEndpointArgs,
    )

    return [call_api_tool, lookup_tool]


def get_tier1_catalog() -> str:
    """Get the Tier 1 endpoint catalog for the planner prompt."""
    return TIER1_CATALOG


def get_endpoint_schema(method: str, path: str) -> str:
    """Get the schema for a specific endpoint (for self-heal context)."""
    key = f"{method.upper()} {path}"
    return ENDPOINT_SCHEMAS.get(key, "(no schema available)")
