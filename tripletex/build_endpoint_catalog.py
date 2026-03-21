#!/usr/bin/env python3
"""Build compact endpoint catalog from swagger.json.

Generates endpoint_catalog.py with:
  - TIER1_CATALOG: common accounting endpoints for the planner prompt
  - FULL_CATALOG: all endpoints for the lookup_endpoint tool
  - ENDPOINT_SCHEMAS: per-endpoint schema strings for self-heal
  - ENDPOINT_CARDS: rich cards for priority endpoints (~35 ops)
  - ENDPOINT_INDEX: lightweight index for ALL ~800 operations

Usage:
    python3 build_endpoint_catalog.py                    # generates endpoint_catalog.py
    python3 build_endpoint_catalog.py --preview          # print catalog to stdout
    python3 build_endpoint_catalog.py --schema Customer  # show one schema
    python3 build_endpoint_catalog.py --stats            # show catalog statistics
"""

import argparse
import json
import os
import sys
import textwrap

import yaml

SWAGGER_PATH = os.path.join(os.path.dirname(__file__), "swagger.json")
OVERRIDES_PATH = os.path.join(os.path.dirname(__file__), "docs", "scripts", "curated_overrides.yaml")

# Read-only / server-generated fields to skip everywhere
READONLY_FIELDS = frozenset({
    "id", "version", "changes", "url", "displayName", "displayNameInklMatrikkel",
    "companyId", "systemGenerated", "isDeletable", "isProxy",
    "addressAsString",
})

# Tier 1: common accounting entity tags to always include in the planner prompt
TIER1_TAGS = {
    "employee", "employee/entitlement", "customer", "supplier", "product",
    "order", "order/orderline",
    "invoice", "invoice/paymentType", "project", "project/participant",
    "department", "company",
    "ledger/voucher", "ledger/account", "ledger/vatType",
    "travelExpense", "travelExpense/cost", "travelExpense/perDiemCompensation",
    "contact", "currency", "country",
    # Salary/payroll
    "salary/transaction", "salary/payslip", "salary/type",
    "employee/employment", "employee/employment/details",
}

def load_overrides():
    """Load curated overrides from YAML. Returns flat dict keyed by 'METHOD /path'."""
    if not os.path.exists(OVERRIDES_PATH):
        print(f"WARNING: {OVERRIDES_PATH} not found, using empty overrides", file=sys.stderr)
        return {}
    with open(OVERRIDES_PATH) as f:
        raw = yaml.safe_load(f) or {}
    flat = {}
    for category_key, category_val in raw.items():
        if not isinstance(category_val, dict):
            continue
        # Category-level notes apply to all endpoints in category
        cat_notes = category_val.get("notes", [])
        for ep_key, ep_val in category_val.items():
            if ep_key == "notes":
                continue
            if not isinstance(ep_val, dict):
                continue
            entry = dict(ep_val)
            # Merge category-level notes
            if cat_notes:
                entry.setdefault("notes", [])
                entry["notes"] = cat_notes + entry["notes"]
            flat[ep_key] = entry
    return flat


def _build_gotcha_notes(overrides):
    """Build GOTCHA_NOTES dict from curated overrides (notes only, not do_not_send which is shown separately)."""
    notes = {}
    for ep_key, ep_val in overrides.items():
        parts = []
        for n in ep_val.get("notes", []):
            parts.append(n)
        if parts:
            notes[ep_key] = "NOTE: " + " | ".join(parts[:3])
    # Hardcoded fallbacks for endpoints not in overrides
    notes.setdefault("POST /invoice", "NOTE: AVOID — prefer POST /order + PUT /order/{id}/:invoice. If used: invoiceDueDate REQUIRED.")
    notes.setdefault("GET /company", "NOTE: Singleton endpoint — returns the single company. No ID needed.")
    return notes


# Loaded at build time
_OVERRIDES = None
GOTCHA_NOTES = {}  # Populated in main() after loading overrides

# ~35 operations that the agent actually uses — get full endpoint cards
PRIORITY_ENDPOINTS = {
    # Core CRUD
    "POST /customer", "GET /customer", "POST /customer/list",
    "POST /supplier", "GET /supplier",
    "POST /employee", "GET /employee",
    "POST /department", "GET /department",
    "POST /product", "POST /product/list", "GET /product",
    "POST /order", "GET /order",
    "POST /invoice", "GET /invoice",
    "POST /project", "GET /project",
    "POST /contact", "GET /contact",
    # Action endpoints
    "PUT /order/{id}/:invoice", "PUT /invoice/{id}/:payment",
    "PUT /invoice/{id}/:send", "PUT /invoice/{id}/:createCreditNote",
    "PUT /employee/entitlement/:grantEntitlementsByTemplate",
    # Lookups
    "GET /invoice/paymentType", "GET /ledger/vatType", "GET /ledger/account",
    "GET /salary/type",
    # Salary/payroll
    "POST /salary/transaction", "GET /salary/payslip",
    "POST /employee/employment", "POST /employee/employment/details",
    # Voucher
    "POST /ledger/voucher", "GET /ledger/voucher",
    # Travel
    "POST /travelExpense",
    "POST /travelExpense/cost",
    "POST /travelExpense/perDiemCompensation",
    # Company
    "PUT /company", "GET /company",
}

# Patches swagger schema gaps with known requirements from real API errors
FIELD_OVERRIDES = {
    "Order.deliveryDate": {"required": True, "note": "Use orderDate if not specified"},
    "Employee.userType": {"required": True, "enum": ["STANDARD", "EXTENDED", "NO_ACCESS"]},
    "Employee.department": {"required": True, "note": "Must create department first"},
    "Product.priceIncludingVatCurrency": {"conflicts_with": "priceExcludingVatCurrency"},
    "OrderLine.unitPriceIncludingVatCurrency": {"conflicts_with": "unitPriceExcludingVatCurrency"},
    "Posting.account": {"required": True},
    "Posting.amount": {"required": True},
    "EmploymentDetails.employmentType": {"required": True, "default": "ORDINARY"},
    "EmploymentDetails.employmentForm": {"required": True, "default": "PERMANENT"},
    "EmploymentDetails.remunerationType": {"required": True, "default": "MONTHLY_WAGE"},
    "EmploymentDetails.workingHoursScheme": {"required": True, "default": "NOT_SHIFT"},
    "EmploymentDetails.annualSalary": {"note": "Required for MONTHLY_WAGE remunerationType"},
    "EmploymentDetails.hourlyWage": {"note": "Required for HOURLY_WAGE remunerationType"},
    "Project.startDate": {"required": True, "note": "Use today's date if not specified"},
    "Invoice.invoiceDueDate": {"required": True, "note": "Default to invoiceDate + 14 days"},
    "PerDiemCompensation.location": {"required": True, "note": "Destination city name, e.g. 'Kristiansand'"},
}


def load_spec():
    with open(SWAGGER_PATH) as f:
        return json.load(f)


def resolve_ref(spec, ref):
    """Resolve $ref to schema dict."""
    parts = ref.replace("#/", "").split("/")
    obj = spec
    for p in parts:
        obj = obj[p]
    return obj


def _get_field_info(spec, schema_name, prop_name, prop_def):
    """Build a structured field info dict for a single property."""
    info = {}
    ref = prop_def.get("$ref", "")
    ptype = prop_def.get("type", "")

    # Check overrides
    override_key = f"{schema_name}.{prop_name}"
    override = FIELD_OVERRIDES.get(override_key, {})

    if ref:
        ref_name = ref.split("/")[-1]
        if ref_name in ("Address", "DeliveryAddress"):
            info["type"] = "object"
            info["note"] = "Fields: addressLine1, postalCode, city"
        elif ref_name == "TravelDetails":
            info["type"] = "object"
            info["note"] = "Fields: departureDate, returnDate, departureFrom, destination, purpose"
        else:
            info["type"] = "ref"
    elif ptype == "array":
        items = prop_def.get("items", {})
        item_ref = items.get("$ref", "")
        if item_ref:
            item_name = item_ref.split("/")[-1]
            info["type"] = "array"
            info["items_schema"] = item_name
            # Expand one level deeper for priority schemas
            info["items_fields"] = _expand_schema_fields(spec, item_name)
        else:
            item_type = items.get("type", "any")
            info["type"] = f"array[{item_type}]"
    else:
        type_map = {"integer": "int", "number": "num", "boolean": "bool", "string": "str"}
        info["type"] = type_map.get(ptype, "str")
        enum = prop_def.get("enum", [])
        if enum:
            info["enum"] = enum

    # Apply overrides
    if override.get("required"):
        info["required"] = True
    if "enum" in override:
        info["enum"] = override["enum"]
    if "default" in override:
        info["default"] = override["default"]
    if "note" in override:
        info["note"] = override.get("note", "")
    if "conflicts_with" in override:
        info["conflicts_with"] = override["conflicts_with"]

    return info


def _expand_schema_fields(spec, schema_name):
    """Expand a schema into a dict of field_name -> field_info, one level only."""
    schemas = spec.get("components", {}).get("schemas", {})
    if schema_name not in schemas:
        return {}
    schema = schemas[schema_name]
    props = schema.get("properties", {})
    required_fields = set(schema.get("required", []))
    fields = {}
    for prop_name, prop_def in props.items():
        if prop_name in READONLY_FIELDS:
            continue
        if prop_def.get("readOnly"):
            continue

        ref = prop_def.get("$ref", "")
        ptype = prop_def.get("type", "")
        is_req = prop_name in required_fields

        field = {}
        override_key = f"{schema_name}.{prop_name}"
        override = FIELD_OVERRIDES.get(override_key, {})

        if ref:
            field["type"] = "ref"
        elif ptype == "array":
            items = prop_def.get("items", {})
            item_ref = items.get("$ref", "")
            if item_ref:
                field["type"] = "array"
                field["items_schema"] = item_ref.split("/")[-1]
            else:
                field["type"] = f"array[{items.get('type', 'any')}]"
        else:
            type_map = {"integer": "int", "number": "num", "boolean": "bool", "string": "str"}
            field["type"] = type_map.get(ptype, "str")
            enum = prop_def.get("enum", [])
            if enum:
                field["enum"] = enum

        if is_req or override.get("required"):
            field["required"] = True
        if "enum" in override:
            field["enum"] = override["enum"]
        if "default" in override:
            field["default"] = override["default"]
        if "note" in override:
            field["note"] = override["note"]
        if "conflicts_with" in override:
            field["conflicts_with"] = override["conflicts_with"]

        fields[prop_name] = field
    return fields


def build_endpoint_card(spec, method, path, overrides=None):
    """Build a rich endpoint card with full field detail for a priority endpoint."""
    method_lower = method.lower()
    op = spec["paths"][path][method_lower]

    tag = (op.get("tags") or ["other"])[0]
    summary = op.get("summary", op.get("description", "")).replace("\n", " ").strip()
    operation_id = op.get("operationId", "")

    card = {
        "op": f"{method} {path}",
        "tag": tag,
        "summary": summary,
        "operationId": operation_id,
        "params": {},
        "fields": {},
        "conflicts": [],
        "gotchas": [],
        "response_shape": "",
        # New curated fields
        "send_exactly": "",
        "do_not_send": [],
        "common_errors": [],
        "prerequisites": [],
    }

    # Query params
    params = [p for p in op.get("parameters", []) if p.get("in") == "query"]
    for p in params:
        ptype = p.get("schema", {}).get("type", "string")
        type_map = {"integer": "int", "number": "num", "boolean": "bool", "string": "str"}
        card["params"][p["name"]] = {
            "type": type_map.get(ptype, "str"),
            "required": p.get("required", False),
            "description": p.get("description", "")[:80],
        }

    # Body fields
    schema_name = get_schema_name_for_body(spec, path, method_lower)
    if schema_name:
        base_name = schema_name.rstrip("[]")
        schemas = spec.get("components", {}).get("schemas", {})
        if base_name in schemas:
            schema = schemas[base_name]
            props = schema.get("properties", {})
            required_fields = set(schema.get("required", []))

            for prop_name, prop_def in props.items():
                if prop_name in READONLY_FIELDS:
                    continue
                if prop_def.get("readOnly"):
                    continue

                field = _get_field_info(spec, base_name, prop_name, prop_def)
                if prop_name in required_fields:
                    field["required"] = True
                card["fields"][prop_name] = field

    # Build conflicts list from field overrides
    conflict_pairs = set()
    for field_name, field_info in card["fields"].items():
        if "conflicts_with" in field_info:
            pair = tuple(sorted([field_name, field_info["conflicts_with"]]))
            conflict_pairs.add(pair)
    card["conflicts"] = [list(p) for p in conflict_pairs]

    # Gotchas from GOTCHA_NOTES
    key = f"{method} {path}"
    if key in GOTCHA_NOTES:
        note = GOTCHA_NOTES[key].replace("NOTE: ", "")
        card["gotchas"].append(note)

    # Enrich with curated overrides
    if overrides and key in overrides:
        ov = overrides[key]
        if ov.get("send_exactly"):
            card["send_exactly"] = ov["send_exactly"].strip()
        if ov.get("do_not_send"):
            card["do_not_send"] = ov["do_not_send"]
        if ov.get("common_errors"):
            card["common_errors"] = ov["common_errors"]
        if ov.get("prerequisites"):
            card["prerequisites"] = ov["prerequisites"]

    # Response shape
    resp_name = get_response_schema_name(spec, path, method_lower)
    if resp_name:
        card["response_shape"] = f"value.{{id, version, ...}} ({resp_name})"

    return card


def build_endpoint_index(spec):
    """Build a lightweight index dict for ALL operations (searchable)."""
    index = {}
    for path in sorted(spec["paths"].keys()):
        path_def = spec["paths"][path]
        for method in ("get", "post", "put", "delete"):
            if method not in path_def:
                continue
            op = path_def[method]
            method_upper = method.upper()
            key = f"{method_upper} {path}"

            tag = (op.get("tags") or ["other"])[0]
            summary = op.get("summary", op.get("description", "")).replace("\n", " ").strip()
            if len(summary) > 100:
                summary = summary[:97] + "..."
            operation_id = op.get("operationId", "")

            has_body = bool(op.get("requestBody"))
            body_schema_name = None
            field_names = []
            if has_body and method in ("post", "put"):
                body_schema_name = get_schema_name_for_body(spec, path, method)
                if body_schema_name:
                    base_name = body_schema_name.rstrip("[]")
                    schemas = spec.get("components", {}).get("schemas", {})
                    if base_name in schemas:
                        props = schemas[base_name].get("properties", {})
                        field_names = [
                            p for p in props
                            if p not in READONLY_FIELDS and not props[p].get("readOnly")
                        ]

            params = [p for p in op.get("parameters", []) if p.get("in") == "query"]
            param_names = [p["name"] for p in params]

            is_action = ":" in path.split("/")[-1]

            index[key] = {
                "tag": tag,
                "summary": summary,
                "operationId": operation_id,
                "has_body": has_body,
                "body_schema_name": body_schema_name,
                "field_names": field_names,
                "param_names": param_names,
                "is_action": is_action,
            }
    return index


def format_schema_compact(spec, schema_name, depth=0, max_depth=1, enriched=False):
    """Format a schema as a compact one-liner showing field names and types.

    Returns string like: {name(str,REQ), email(str), customer:{id}, orderLines:[{...}]}
    If enriched=True, adds [REQ], [REQ*], conflict annotations, and field descriptions for priority endpoints.
    """
    schemas = spec.get("components", {}).get("schemas", {})
    if schema_name not in schemas:
        return "{...}"

    schema = schemas[schema_name]
    props = schema.get("properties", {})
    required_fields = set(schema.get("required", []))

    parts = []
    for prop_name, prop_def in props.items():
        if prop_name in READONLY_FIELDS:
            continue
        if prop_def.get("readOnly"):
            continue

        ref = prop_def.get("$ref", "")
        ptype = prop_def.get("type", "")
        is_req = prop_name in required_fields

        # Check overrides
        override_key = f"{schema_name}.{prop_name}"
        override = FIELD_OVERRIDES.get(override_key, {})
        is_override_req = override.get("required", False)

        if enriched:
            req_mark = "[REQ]" if is_req else "[REQ*]" if is_override_req else ""
        else:
            req_mark = ",REQ" if is_req else ""

        # Conflict annotation
        conflict_note = ""
        if enriched and "conflicts_with" in override:
            conflict_note = f" [NOT {override['conflicts_with']}]"

        if ref:
            ref_name = ref.split("/")[-1]
            if ref_name in ("Address", "DeliveryAddress"):
                parts.append(f"{prop_name}:{{addressLine1,postalCode,city}}")
            elif ref_name == "TravelDetails":
                parts.append(f"{prop_name}:{{departureDate,returnDate,departureFrom,destination,purpose}}")
            elif depth < max_depth and ref_name not in ("Change",):
                parts.append(f"{prop_name}:{{id}}" + (req_mark if enriched else ""))
            else:
                parts.append(f"{prop_name}:{{id}}" + (req_mark if enriched else ""))
        elif ptype == "array":
            items = prop_def.get("items", {})
            item_ref = items.get("$ref", "")
            if item_ref:
                item_name = item_ref.split("/")[-1]
                if item_name == "OrderLine":
                    if enriched:
                        parts.append(
                            f"{prop_name}:[{{product:{{id}}, description(str), count(num), "
                            f"unitPriceExcludingVatCurrency(num) [NOT unitPriceIncludingVatCurrency], "
                            f"vatType:{{id}}, discount(num)}}]"
                        )
                    else:
                        parts.append(f"{prop_name}:[{{product:{{id}},description,count,unitPriceExcludingVatCurrency}}]")
                elif item_name == "Posting":
                    if enriched:
                        parts.append(
                            f"{prop_name}:[{{account:{{id}}[REQ], amount(num)[REQ], "
                            f"description(str), date(date), vatType:{{id}}, customer:{{id}}, supplier:{{id}}}}]"
                        )
                    else:
                        parts.append(f"{prop_name}:[{{account:{{id}},amount}}]")
                elif item_name == "Payslip":
                    parts.append(
                        f"{prop_name}:[{{employee:{{id}}, date(date), specifications:[{{salaryType:{{id}}, "
                        f"rate(num), count(num), amount(num)}}]}}]"
                    )
                else:
                    parts.append(f"{prop_name}:[{{...}}]")
            else:
                item_type = items.get("type", "any")
                parts.append(f"{prop_name}:[{item_type}]")
        else:
            # Scalar field
            type_map = {"integer": "int", "number": "num", "boolean": "bool", "string": "str"}
            short_type = type_map.get(ptype, "str")

            # Check for enriched enum handling (show all values)
            enum = override.get("enum") or prop_def.get("enum", [])
            if enum:
                if enriched:
                    enum_str = "|".join(str(e) for e in enum)
                else:
                    enum_str = "|".join(str(e) for e in enum[:5])
                    if len(enum) > 5:
                        enum_str += "|..."
                parts.append(f"{prop_name}({enum_str}){req_mark}{conflict_note}")
            else:
                fmt = prop_def.get("format", "")
                if enriched and fmt == "date":
                    short_type = "date"
                parts.append(f"{prop_name}({short_type}){req_mark}{conflict_note}")

    return "{" + ", ".join(parts) + "}"


def format_query_params(spec, path, method):
    """Format query parameters compactly."""
    op = spec["paths"][path][method]
    params = [p for p in op.get("parameters", []) if p.get("in") == "query"]
    if not params:
        return ""

    parts = []
    for p in params:
        name = p["name"]
        ptype = p.get("schema", {}).get("type", "string")
        type_map = {"integer": "int", "number": "num", "boolean": "bool", "string": "str"}
        short_type = type_map.get(ptype, "str")
        req = ",REQ" if p.get("required") else ""
        parts.append(f"{name}({short_type}{req})")

    return "  Params: " + ", ".join(parts)


def get_schema_name_for_body(spec, path, method):
    """Extract schema name from request body."""
    op = spec["paths"][path][method]
    rb = op.get("requestBody", {})
    content = rb.get("content", {})
    for ct, schema_info in content.items():
        ref = schema_info.get("schema", {}).get("$ref", "")
        if ref:
            return ref.split("/")[-1]
        # Check for array of refs
        items = schema_info.get("schema", {}).get("items", {})
        item_ref = items.get("$ref", "")
        if item_ref:
            return item_ref.split("/")[-1] + "[]"
    return None


def get_response_schema_name(spec, path, method):
    """Extract schema name from 200/201 response."""
    op = spec["paths"][path][method]
    for code in ("200", "201"):
        resp = op.get("responses", {}).get(code, {})
        content = resp.get("content", {})
        for ct, schema_info in content.items():
            ref = schema_info.get("schema", {}).get("$ref", "")
            if ref:
                name = ref.split("/")[-1]
                for prefix in ("ListResponse", "ResponseWrapper"):
                    if name.startswith(prefix):
                        return name[len(prefix):]
                return name
    return None


def build_catalog(spec, overrides=None):
    """Build the full endpoint catalog organized by tag.

    For priority endpoints with send_exactly in overrides, uses the curated
    minimal body instead of the full schema expansion (saves ~5K tokens).
    """
    overrides = overrides or {}
    catalog = {}  # tag -> list of endpoint strings

    for path in sorted(spec["paths"].keys()):
        path_def = spec["paths"][path]
        for method in ("get", "post", "put", "delete"):
            if method not in path_def:
                continue
            op = path_def[method]

            # Get the primary tag
            tags = op.get("tags", ["other"])
            tag = tags[0] if tags else "other"

            # Get summary/description
            summary = op.get("summary", op.get("description", ""))
            summary = summary.replace("\n", " ").strip()
            if len(summary) > 100:
                summary = summary[:97] + "..."

            method_upper = method.upper()
            key = f"{method_upper} {path}"
            line = f"{method_upper} {path} — {summary}"

            has_body = bool(op.get("requestBody"))
            is_priority = key in PRIORITY_ENDPOINTS
            ov = overrides.get(key, {})

            # Body: use send_exactly for priority endpoints if available
            if is_priority and ov.get("send_exactly"):
                send_ex = ov["send_exactly"].strip()
                # Compact the JSON to one-ish line for the catalog
                compact = _compact_send_exactly(send_ex)
                line += f"\n  Send: {compact}"
                # Add do_not_send warnings
                for dns in ov.get("do_not_send", []):
                    line += f"\n  ⊘ {dns['field']} — {dns['reason']}"
            elif has_body and method in ("post", "put"):
                schema_name = get_schema_name_for_body(spec, path, method)
                if schema_name:
                    is_array = schema_name.endswith("[]")
                    base_name = schema_name.rstrip("[]")
                    body_str = format_schema_compact(spec, base_name, enriched=is_priority)
                    if is_array:
                        line += f"\n  Body: [{body_str}]"
                    else:
                        line += f"\n  Body: {body_str}"

            # Query params
            params = [p for p in op.get("parameters", []) if p.get("in") == "query"]
            if params:
                param_parts = []
                for p in params:
                    name = p["name"]
                    ptype = p.get("schema", {}).get("type", "string")
                    type_map = {"integer": "int", "number": "num", "boolean": "bool", "string": "str"}
                    short_type = type_map.get(ptype, "str")
                    req = ",REQ" if p.get("required") else ""
                    param_parts.append(f"{name}({short_type}{req})")
                line += f"\n  Params: {', '.join(param_parts)}"

            # Gotcha notes (from overrides or hardcoded fallback)
            if key in GOTCHA_NOTES:
                line += f"\n  {GOTCHA_NOTES[key]}"

            # Override notes for priority endpoints (only if no send_exactly)
            if is_priority and not ov.get("send_exactly"):
                schema_name = get_schema_name_for_body(spec, path, method) if has_body else None
                if schema_name:
                    base_name = schema_name.rstrip("[]")
                    for field_name in list(FIELD_OVERRIDES.keys()):
                        if field_name.startswith(base_name + "."):
                            override = FIELD_OVERRIDES[field_name]
                            fname = field_name.split(".")[-1]
                            if "note" in override and key not in GOTCHA_NOTES:
                                line += f"\n  NOTE: {fname} — {override['note']}"

            if tag not in catalog:
                catalog[tag] = []
            catalog[tag].append(line)

    return catalog


def _compact_send_exactly(send_exactly_str):
    """Compact a multi-line send_exactly JSON into a readable one-liner.

    Example: '{customer:{id}, orderDate:"YYYY-MM-DD", deliveryDate:"YYYY-MM-DD", orderLines:[{description, count, unitPriceExcludingVatCurrency}]}'
    """
    import re
    s = send_exactly_str.strip()
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s)
    # Remove quotes around placeholder values but keep field names readable
    s = s.replace('"<string>"', '"..."')
    s = s.replace('"<city name>"', '"..."')
    s = s.replace('"YYYY-MM-DD"', '"date"')
    s = s.replace('<int>', 'N')
    s = s.replace('<number>', 'N')
    s = s.replace('<number_of_days>', 'N')
    s = s.replace('<positive_for_debit>', '+N')
    s = s.replace('<negative_for_credit>', '-N')
    return s


def build_slim_catalog(spec, overrides):
    """Build a compact catalog of only curated endpoints (~5-8K tokens).

    Used in the planner prompt instead of the full TIER1_CATALOG (53K tokens).
    Only includes endpoints from curated_overrides.yaml with their Send Exactly
    bodies, notes, and query params. The planner uses lookup_endpoint for anything else.
    """
    lines = []
    lines.append("## Curated Endpoints (use lookup_endpoint for anything not listed here)\n")

    for ep_key, ep_val in overrides.items():
        # Parse method and path
        parts = ep_key.split(" ", 1)
        if len(parts) != 2:
            continue
        method, path = parts

        # Get summary from spec if available
        summary = ""
        method_lower = method.lower()
        if path in spec.get("paths", {}) and method_lower in spec["paths"][path]:
            op = spec["paths"][path][method_lower]
            summary = op.get("summary", "").replace("\n", " ").strip()[:80]

        line = f"{method} {path}"
        if summary:
            line += f" — {summary}"

        # Send Exactly body (compact)
        if ep_val.get("send_exactly"):
            compact = _compact_send_exactly(ep_val["send_exactly"])
            line += f"\n  Send: {compact}"

        # Query params from spec
        if path in spec.get("paths", {}) and method_lower in spec["paths"][path]:
            op = spec["paths"][path][method_lower]
            params = [p for p in op.get("parameters", []) if p.get("in") == "query"]
            if params:
                param_parts = []
                for p in params[:8]:  # Limit to 8 most important params
                    name = p["name"]
                    req = ",REQ" if p.get("required") else ""
                    param_parts.append(f"{name}{req}")
                line += f"\n  Params: {', '.join(param_parts)}"

        # Do not send
        for dns in ep_val.get("do_not_send", []):
            line += f"\n  ⊘ {dns['field']} — {dns['reason']}"

        # Notes (max 2)
        for note in ep_val.get("notes", [])[:2]:
            line += f"\n  ! {note}"

        # Prerequisites
        for prereq in ep_val.get("prerequisites", []):
            line += f"\n  Requires: {prereq}"

        lines.append(line)

    return "\n\n".join(lines)


def build_endpoint_schemas(spec, overrides=None):
    """Build per-endpoint schema dict for self-heal context.

    When curated overrides include send_exactly and common_errors, they're
    appended to give self-heal prompts actionable fix info.
    """
    overrides = overrides or {}
    schemas = {}
    for path in spec["paths"]:
        path_def = spec["paths"][path]
        for method in ("get", "post", "put", "delete"):
            if method not in path_def:
                continue
            op = path_def[method]
            key = f"{method.upper()} {path}"

            parts = []

            # Query params
            params = [p for p in op.get("parameters", []) if p.get("in") == "query"]
            if params:
                param_strs = []
                for p in params:
                    name = p["name"]
                    ptype = p.get("schema", {}).get("type", "string")
                    req = " (REQUIRED)" if p.get("required") else ""
                    desc = p.get("description", "")[:50]
                    param_strs.append(f"  {name}: {ptype}{req} — {desc}")
                parts.append("Query params:\n" + "\n".join(param_strs))

            # Body schema
            has_body = bool(op.get("requestBody"))
            if has_body and method in ("post", "put"):
                schema_name = get_schema_name_for_body(spec, path, method)
                if schema_name:
                    base_name = schema_name.rstrip("[]")
                    body_str = format_schema_compact(spec, base_name)
                    parts.append(f"Body schema ({base_name}): {body_str}")

            # Curated overrides: send_exactly + common_errors
            ov = overrides.get(key, {})
            if ov.get("send_exactly"):
                parts.append(f"Send exactly:\n{ov['send_exactly'].strip()}")
            if ov.get("common_errors"):
                err_lines = []
                for ce in ov["common_errors"]:
                    err_lines.append(f"  {ce['symptom']} → {ce['fix']}")
                parts.append("Common errors:\n" + "\n".join(err_lines))
            if ov.get("do_not_send"):
                dns_lines = [f"  {d['field']} — {d['reason']}" for d in ov["do_not_send"]]
                parts.append("Do NOT send:\n" + "\n".join(dns_lines))

            if parts:
                schemas[key] = "\n\n".join(parts)
            else:
                schemas[key] = "(no body or query params)"

    return schemas


def generate_output(spec, overrides=None):
    """Generate the endpoint_catalog.py file content."""
    overrides = overrides or {}
    catalog = build_catalog(spec, overrides)
    endpoint_schemas = build_endpoint_schemas(spec, overrides)
    endpoint_cards = {}
    endpoint_index = build_endpoint_index(spec)

    # Build endpoint cards for priority endpoints
    for path in spec["paths"]:
        path_def = spec["paths"][path]
        for method in ("get", "post", "put", "delete"):
            if method not in path_def:
                continue
            key = f"{method.upper()} {path}"
            if key in PRIORITY_ENDPOINTS:
                endpoint_cards[key] = build_endpoint_card(spec, method.upper(), path, overrides)

    # Build tier1 and tier2 text
    tier1_lines = []
    tier2_lines = []

    for tag in sorted(catalog.keys()):
        entries = catalog[tag]
        section = f"\n### {tag}\n" + "\n".join(entries)

        if tag in TIER1_TAGS:
            tier1_lines.append(section)
        else:
            tier2_lines.append(section)

    tier1_text = "\n".join(tier1_lines)
    tier2_text = "\n".join(tier2_lines)
    full_text = tier1_text + "\n\n---\n" + tier2_text

    # Generate Python file
    output = '"""Auto-generated endpoint catalog from swagger.json.\n\n'
    output += 'Do not edit manually. Regenerate with: python3 build_endpoint_catalog.py\n"""\n\n'

    # SLIM_CATALOG (curated endpoints only — for planner prompt, ~5-8K tokens)
    slim_text = build_slim_catalog(spec, overrides)
    output += "SLIM_CATALOG = " + repr(slim_text) + "\n\n"

    # TIER1_CATALOG (kept for lookup_endpoint searches)
    output += "TIER1_CATALOG = " + repr(tier1_text) + "\n\n"

    # FULL_CATALOG (tier1 + tier2, for lookup_endpoint)
    output += "FULL_CATALOG = " + repr(full_text) + "\n\n"

    # ENDPOINT_SCHEMAS dict
    output += "ENDPOINT_SCHEMAS = " + repr(endpoint_schemas) + "\n\n"

    # ENDPOINT_CARDS dict (rich cards for priority endpoints)
    output += "ENDPOINT_CARDS = " + repr(endpoint_cards) + "\n\n"

    # ENDPOINT_INDEX dict (lightweight index for all operations)
    output += "ENDPOINT_INDEX = " + repr(endpoint_index) + "\n"

    return output


def main():
    global GOTCHA_NOTES, _OVERRIDES

    parser = argparse.ArgumentParser(description="Build endpoint catalog from swagger.json")
    parser.add_argument("--preview", action="store_true", help="Print catalog to stdout instead of generating file")
    parser.add_argument("--schema", type=str, help="Show compact schema for a specific schema name")
    parser.add_argument("--stats", action="store_true", help="Show catalog statistics")
    args = parser.parse_args()

    spec = load_spec()
    _OVERRIDES = load_overrides()
    GOTCHA_NOTES = _build_gotcha_notes(_OVERRIDES)
    print(f"Loaded {len(_OVERRIDES)} curated endpoint overrides")

    if args.schema:
        print(format_schema_compact(spec, args.schema))
        return

    catalog = build_catalog(spec, _OVERRIDES)

    if args.stats:
        tier1_count = sum(len(v) for k, v in catalog.items() if k in TIER1_TAGS)
        tier2_count = sum(len(v) for k, v in catalog.items() if k not in TIER1_TAGS)
        print(f"Tier 1 tags: {len([t for t in catalog if t in TIER1_TAGS])}")
        print(f"Tier 1 endpoints: {tier1_count}")
        print(f"Tier 2 tags: {len([t for t in catalog if t not in TIER1_TAGS])}")
        print(f"Tier 2 endpoints: {tier2_count}")
        print(f"Total endpoints: {tier1_count + tier2_count}")

        # Estimate token count (rough: 4 chars ≈ 1 token)
        tier1_text = "\n".join(
            f"\n### {tag}\n" + "\n".join(catalog[tag])
            for tag in sorted(catalog) if tag in TIER1_TAGS
        )
        print(f"Tier 1 chars: {len(tier1_text)} (~{len(tier1_text)//4} tokens)")

        # Card/index stats
        endpoint_index = build_endpoint_index(spec)
        priority_count = sum(
            1 for path in spec["paths"]
            for method in ("get", "post", "put", "delete")
            if method in spec["paths"][path] and f"{method.upper()} {path}" in PRIORITY_ENDPOINTS
        )
        print(f"Endpoint cards (priority): {priority_count}")
        print(f"Endpoint index (all): {len(endpoint_index)}")

        # Count endpoints with curated send_exactly
        curated_count = sum(1 for k in PRIORITY_ENDPOINTS if k in _OVERRIDES and _OVERRIDES[k].get("send_exactly"))
        print(f"Endpoints with curated send_exactly: {curated_count}")
        return

    if args.preview:
        for tag in sorted(catalog.keys()):
            is_tier1 = tag in TIER1_TAGS
            marker = "[T1]" if is_tier1 else "[T2]"
            print(f"\n{marker} ### {tag}")
            for entry in catalog[tag]:
                print(entry)
        return

    # Generate endpoint_catalog.py
    output = generate_output(spec, _OVERRIDES)
    output_path = os.path.join(os.path.dirname(__file__), "endpoint_catalog.py")
    with open(output_path, "w") as f:
        f.write(output)
    print(f"Generated {output_path}")

    # Print stats
    tier1_count = sum(len(v) for k, v in catalog.items() if k in TIER1_TAGS)
    tier2_count = sum(len(v) for k, v in catalog.items() if k not in TIER1_TAGS)
    print(f"Tier 1: {tier1_count} endpoints, Tier 2: {tier2_count} endpoints")


if __name__ == "__main__":
    main()
