"""Generic Tripletex API tools — call_api + lookup_endpoint."""

import json
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from endpoint_catalog import (
    ENDPOINT_CARDS,
    ENDPOINT_INDEX,
    ENDPOINT_SCHEMAS,
    FULL_CATALOG,
    TIER1_CATALOG,
)

# Synonym map for scored multi-field search
SYNONYMS = {
    "payroll": ["salary", "transaction", "payslip", "wage"],
    "bill": ["invoice"], "worker": ["employee", "employment"],
    "receipt": ["voucher"], "timesheet": ["timesheet", "entry", "hours"],
    "wage": ["salary", "employment"],
    "bonus": ["salary", "transaction", "specification"],
    "account": ["ledger", "account"], "tax": ["vatType", "vat", "tax"],
    "hours": ["timesheet", "entry"],
    "nómina": ["salary", "payroll"], "lønn": ["salary", "payroll"],
    "Gehalt": ["salary", "payroll"], "facture": ["invoice"],
    "commande": ["order"], "fournisseur": ["supplier"],
    "Rechnung": ["invoice"], "Bestellung": ["order"],
    "salaire": ["salary", "payroll"], "salário": ["salary", "payroll"],
    "prima": ["salary", "bonus"], "Prämie": ["salary", "bonus"],
    "bonificación": ["salary", "bonus"],
}


class CallApiArgs(BaseModel):
    method: str = Field(description="HTTP method: GET, POST, PUT, or DELETE")
    path: str = Field(description="API path with IDs substituted, e.g. /customer/123")
    query_params: Optional[dict] = Field(default=None, description="Query parameters as dict")
    body: Optional[dict | list] = Field(default=None, description="Request body (camelCase). Dict for single, list for bulk /list endpoints.")


class LookupEndpointArgs(BaseModel):
    query: str = Field(description="Search keywords, e.g. 'supplier', 'payment type', 'voucher posting'")


def _format_card_for_lookup(card: dict) -> str:
    """Format a rich endpoint card as readable text for lookup results."""
    lines = [f"{card['op']} [{card['tag']}]", f"  Summary: {card['summary']}"]
    if card.get("fields"):
        field_strs = []
        for fname, finfo in card["fields"].items():
            ftype = finfo.get("type", "?")
            req = " [REQ]" if finfo.get("required") else ""
            note = f" — {finfo['note']}" if finfo.get("note") else ""
            enum = f" ({', '.join(str(e) for e in finfo['enum'])})" if finfo.get("enum") else ""
            conflict = f" [NOT {finfo['conflicts_with']}]" if finfo.get("conflicts_with") else ""
            if ftype == "array" and finfo.get("items_fields"):
                sub_fields = ", ".join(finfo["items_fields"].keys())
                field_strs.append(f"{fname}([{{{sub_fields}}}]){req}")
            else:
                field_strs.append(f"{fname}({ftype}){req}{enum}{conflict}{note}")
        lines.append(f"  Body fields: {', '.join(field_strs)}")
    if card.get("params"):
        param_strs = [f"{k}({v['type']})" for k, v in card["params"].items()]
        lines.append(f"  Params: {', '.join(param_strs)}")
    if card.get("gotchas"):
        for g in card["gotchas"]:
            lines.append(f"  GOTCHA: {g}")
    if card.get("conflicts"):
        for pair in card["conflicts"]:
            lines.append(f"  CONFLICT: {pair[0]} vs {pair[1]} — send only one")
    return "\n".join(lines)


def _format_index_entry(op_key: str, idx: dict) -> str:
    """Format a lightweight index entry as readable text."""
    lines = [f"{op_key} [{idx['tag']}]", f"  Summary: {idx['summary']}"]
    if idx.get("field_names"):
        lines.append(f"  Body fields: {', '.join(idx['field_names'][:15])}")
        if len(idx["field_names"]) > 15:
            lines[-1] += ", ..."
    if idx.get("param_names"):
        lines.append(f"  Params: {', '.join(idx['param_names'][:10])}")
        if len(idx["param_names"]) > 10:
            lines[-1] += ", ..."
    return "\n".join(lines)


def _format_card_for_self_heal(card: dict) -> str:
    """Format a rich endpoint card for self-heal context (more detail than lookup)."""
    lines = [f"{card['op']} — {card['summary']}"]
    if card.get("fields"):
        lines.append("Body fields:")
        for fname, finfo in card["fields"].items():
            ftype = finfo.get("type", "?")
            req = " (REQUIRED)" if finfo.get("required") else ""
            default = f" default={finfo['default']}" if finfo.get("default") else ""
            note = f" — {finfo['note']}" if finfo.get("note") else ""
            enum = f" enum=[{', '.join(str(e) for e in finfo['enum'])}]" if finfo.get("enum") else ""
            conflict = f" CONFLICTS WITH {finfo['conflicts_with']}" if finfo.get("conflicts_with") else ""
            if ftype == "array" and finfo.get("items_fields"):
                lines.append(f"  {fname}: array of objects{req}")
                for sf_name, sf_info in finfo["items_fields"].items():
                    sf_type = sf_info.get("type", "?")
                    sf_req = " (REQUIRED)" if sf_info.get("required") else ""
                    sf_enum = f" enum=[{', '.join(str(e) for e in sf_info['enum'])}]" if sf_info.get("enum") else ""
                    sf_conflict = f" CONFLICTS WITH {sf_info['conflicts_with']}" if sf_info.get("conflicts_with") else ""
                    lines.append(f"    {sf_name}: {sf_type}{sf_req}{sf_enum}{sf_conflict}")
            else:
                lines.append(f"  {fname}: {ftype}{req}{default}{enum}{conflict}{note}")
    if card.get("params"):
        lines.append("Query params:")
        for pname, pinfo in card["params"].items():
            req = " (REQUIRED)" if pinfo.get("required") else ""
            desc = f" — {pinfo['description']}" if pinfo.get("description") else ""
            lines.append(f"  {pname}: {pinfo['type']}{req}{desc}")
    if card.get("gotchas"):
        lines.append("Gotchas:")
        for g in card["gotchas"]:
            lines.append(f"  - {g}")
    return "\n".join(lines)


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
        keywords = query.lower().split()
        expanded = set(keywords)
        for kw in keywords:
            expanded.update(s.lower() for s in SYNONYMS.get(kw, []))

        scored = []
        for op_key, idx in ENDPOINT_INDEX.items():
            score = 0
            tag_lower = idx["tag"].lower()
            summary_lower = idx["summary"].lower()
            op_id_lower = idx.get("operationId", "").lower()
            fields_str = " ".join(idx.get("field_names", [])).lower()
            params_str = " ".join(idx.get("param_names", [])).lower()

            for kw in expanded:
                if kw in tag_lower:       score += 4
                if kw in op_key.lower():  score += 3
                if kw in op_id_lower:     score += 2
                if kw in summary_lower:   score += 2
                if kw in fields_str:      score += 1
                if kw in params_str:      score += 1

            if score > 0:
                scored.append((score, op_key, idx))

        scored.sort(key=lambda x: -x[0])
        top = scored[:15]

        results = []
        for _score, op_key, idx in top:
            if op_key in ENDPOINT_CARDS:
                results.append(_format_card_for_lookup(ENDPOINT_CARDS[op_key]))
            else:
                results.append(_format_index_entry(op_key, idx))
        return "\n\n".join(results) if results else "No matching endpoints found."

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
    """Get the schema for a specific endpoint (for self-heal context).

    Uses rich card → index + raw schema → raw schema fallback chain.
    """
    key = f"{method.upper()} {path}"

    # Try rich card first (priority endpoints)
    card = ENDPOINT_CARDS.get(key)
    if card:
        return _format_card_for_self_heal(card)

    # Try index entry combined with raw schema
    idx = ENDPOINT_INDEX.get(key)
    if idx:
        raw = ENDPOINT_SCHEMAS.get(key, "")
        return f"[{idx['tag']}] {idx['summary']}\n{raw}"

    # Final fallback
    return ENDPOINT_SCHEMAS.get(key, "(no schema available)")
