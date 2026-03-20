#!/usr/bin/env python3
"""Build compact endpoint catalog from swagger.json.

Generates endpoint_catalog.py with:
  - TIER1_CATALOG: common accounting endpoints for the planner prompt
  - FULL_CATALOG: all endpoints for the lookup_endpoint tool
  - ENDPOINT_SCHEMAS: per-endpoint schema strings for self-heal

Usage:
    python3 build_endpoint_catalog.py                    # generates endpoint_catalog.py
    python3 build_endpoint_catalog.py --preview          # print catalog to stdout
    python3 build_endpoint_catalog.py --schema Customer  # show one schema
"""

import argparse
import json
import os
import sys
import textwrap

SWAGGER_PATH = os.path.join(os.path.dirname(__file__), "swagger.json")

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
    "department",
    "ledger/voucher", "ledger/account", "ledger/vatType",
    "travelExpense", "contact", "currency", "country",
}

# Known gotchas to append as notes
GOTCHA_NOTES = {
    "POST /product": "NOTE: Do NOT send priceIncludingVatCurrency — it conflicts with priceExcludingVatCurrency.",
    "POST /invoice": "NOTE: Company must have a registered bank account first, or this will fail.",
    "POST /employee": "NOTE: department.id may be required even though schema says optional. userType is REQUIRED — use 'STANDARD' for normal employees, 'EXTENDED' for administrators.",
    "POST /ledger/voucher": "NOTE: postings cannot be null — must be a non-empty array.",
    "POST /order": "NOTE: deliveryDate is REQUIRED even though schema says optional. Use orderDate value if not specified.",
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


def format_schema_compact(spec, schema_name, depth=0, max_depth=1):
    """Format a schema as a compact one-liner showing field names and types.

    Returns string like: {name(str,REQ), email(str), customer:{id}, orderLines:[{...}]}
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
        req_mark = ",REQ" if is_req else ""

        if ref:
            ref_name = ref.split("/")[-1]
            # Common pattern: nested objects are usually {id: <int>} references
            # But some like Address/TravelDetails should be expanded
            if ref_name in ("Address", "DeliveryAddress"):
                parts.append(f"{prop_name}:{{addressLine1,postalCode,city}}")
            elif ref_name == "TravelDetails":
                parts.append(f"{prop_name}:{{departureDate,returnDate,departureFrom,destination,purpose}}")
            elif depth < max_depth and ref_name not in ("Change",):
                # Show as {id} reference
                parts.append(f"{prop_name}:{{id}}")
            else:
                parts.append(f"{prop_name}:{{id}}")
        elif ptype == "array":
            items = prop_def.get("items", {})
            item_ref = items.get("$ref", "")
            if item_ref:
                item_name = item_ref.split("/")[-1]
                if item_name == "OrderLine":
                    parts.append(f"{prop_name}:[{{product:{{id}},description,count,unitPriceExcludingVatCurrency}}]")
                elif item_name == "Posting":
                    parts.append(f"{prop_name}:[{{account:{{id}},amount}}]")
                else:
                    parts.append(f"{prop_name}:[{{...}}]")
            else:
                item_type = items.get("type", "any")
                parts.append(f"{prop_name}:[{item_type}]")
        else:
            # Scalar field
            type_map = {"integer": "int", "number": "num", "boolean": "bool", "string": "str"}
            short_type = type_map.get(ptype, "str")
            enum = prop_def.get("enum", [])
            if enum:
                enum_str = "|".join(str(e) for e in enum[:5])
                if len(enum) > 5:
                    enum_str += "|..."
                parts.append(f"{prop_name}({enum_str}{req_mark})")
            else:
                parts.append(f"{prop_name}({short_type}{req_mark})")

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


def build_catalog(spec):
    """Build the full endpoint catalog organized by tag."""
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
            # Clean up and truncate
            summary = summary.replace("\n", " ").strip()
            if len(summary) > 100:
                summary = summary[:97] + "..."

            # Build the endpoint line
            method_upper = method.upper()
            line = f"{method_upper} {path} — {summary}"

            # Add body schema for POST/PUT with request body
            has_body = bool(op.get("requestBody"))
            is_action = ":" in path.split("/")[-1]

            if has_body and method in ("post", "put"):
                schema_name = get_schema_name_for_body(spec, path, method)
                if schema_name:
                    is_array = schema_name.endswith("[]")
                    base_name = schema_name.rstrip("[]")
                    body_str = format_schema_compact(spec, base_name)
                    if is_array:
                        line += f"\n  Body: [{body_str}]"
                    else:
                        line += f"\n  Body: {body_str}"

            # Add query params
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

            # Add gotcha notes
            key = f"{method_upper} {path}"
            if key in GOTCHA_NOTES:
                line += f"\n  {GOTCHA_NOTES[key]}"

            if tag not in catalog:
                catalog[tag] = []
            catalog[tag].append(line)

    return catalog


def build_endpoint_schemas(spec):
    """Build per-endpoint schema dict for self-heal context."""
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

            if parts:
                schemas[key] = "\n".join(parts)
            else:
                schemas[key] = "(no body or query params)"

    return schemas


def generate_output(spec):
    """Generate the endpoint_catalog.py file content."""
    catalog = build_catalog(spec)
    endpoint_schemas = build_endpoint_schemas(spec)

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

    # TIER1_CATALOG
    output += "TIER1_CATALOG = " + repr(tier1_text) + "\n\n"

    # FULL_CATALOG (tier1 + tier2)
    output += "FULL_CATALOG = " + repr(full_text) + "\n\n"

    # ENDPOINT_SCHEMAS dict
    output += "ENDPOINT_SCHEMAS = " + repr(endpoint_schemas) + "\n"

    return output


def main():
    parser = argparse.ArgumentParser(description="Build endpoint catalog from swagger.json")
    parser.add_argument("--preview", action="store_true", help="Print catalog to stdout instead of generating file")
    parser.add_argument("--schema", type=str, help="Show compact schema for a specific schema name")
    parser.add_argument("--stats", action="store_true", help="Show catalog statistics")
    args = parser.parse_args()

    spec = load_spec()

    if args.schema:
        print(format_schema_compact(spec, args.schema))
        return

    catalog = build_catalog(spec)

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
    output = generate_output(spec)
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
