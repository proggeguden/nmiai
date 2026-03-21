#!/usr/bin/env python3
"""
Generate minimal cheat sheets from the Tripletex OpenAPI spec.

Every field, type, and constraint comes directly from the spec.
No hallucinated data.

Usage:
    python3 generate_cheatsheets.py                    # Generate all categories
    python3 generate_cheatsheets.py customer            # Generate one category
    python3 generate_cheatsheets.py --list              # List available categories
    python3 generate_cheatsheets.py --status            # Show generation progress
"""

import json
import os
import sys
import yaml
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_PATH = os.path.join(BASE_DIR, "openapi.json")
OVERRIDES_PATH = os.path.join(BASE_DIR, "scripts", "curated_overrides.yaml")
ENDPOINTS_DIR = os.path.join(BASE_DIR, "endpoints")
STATUS_PATH = os.path.join(BASE_DIR, "scripts", ".generation_status.json")

# Maps our cheat sheet files to the OpenAPI tags they cover
CATEGORY_MAP = {
    "customer": {
        "file": "customer.md",
        "tags": ["customer", "customer/category"],
        "description": "Create and manage customers",
    },
    "supplier": {
        "file": "supplier.md",
        "tags": ["supplier"],
        "description": "Register and manage suppliers",
    },
    "department": {
        "file": "department.md",
        "tags": ["department"],
        "description": "Create departments",
    },
    "employee": {
        "file": "employee.md",
        "tags": ["employee", "employee/category"],
        "description": "Create and manage employees",
    },
    "employee-entitlement": {
        "file": "employee-entitlement.md",
        "tags": ["employee/entitlement"],
        "description": "Grant employee entitlements/permissions",
    },
    "employee-employment": {
        "file": "employee-employment.md",
        "tags": ["employee/employment", "employee/employment/details",
                 "employee/employment/employmentType"],
        "description": "Employment records and details",
    },
    "product": {
        "file": "product.md",
        "tags": ["product", "product/unit", "product/discountGroup"],
        "description": "Create products, bulk create",
    },
    "order": {
        "file": "order.md",
        "tags": ["order", "order/orderline", "order/orderGroup"],
        "description": "Create orders with order lines",
    },
    "order-invoice": {
        "file": "order-invoice.md",
        "tags": [],  # Special: uses specific paths, not tags
        "paths": ["/order/{id}/:invoice", "/order/{id}/:invoiceMultipleOrders"],
        "description": "Convert orders to invoices",
    },
    "invoice-actions": {
        "file": "invoice-actions.md",
        "tags": ["invoice"],
        "description": "Invoice operations: search, payment, send, credit notes",
    },
    "travel-expense": {
        "file": "travel-expense.md",
        "tags": ["travelExpense"],
        "description": "Create travel expense shells",
    },
    "travel-expense-sub": {
        "file": "travel-expense-sub.md",
        "tags": ["travelExpense/cost", "travelExpense/costCategory",
                 "travelExpense/perDiemCompensation", "travelExpense/paymentType",
                 "travelExpense/mileageAllowance", "travelExpense/accommodationAllowance"],
        "description": "Travel expense sub-resources: costs, per diem, mileage",
    },
    "voucher": {
        "file": "voucher.md",
        "tags": ["ledger/voucher", "ledger/voucherType"],
        "description": "Create vouchers with postings",
    },
    "ledger-lookup": {
        "file": "ledger-lookup.md",
        "tags": ["ledger/account", "ledger/vatType", "ledger/posting"],
        "description": "Look up accounts, VAT types, postings",
    },
    "salary-transaction": {
        "file": "salary-transaction.md",
        "tags": ["salary/transaction", "salary/payslip", "salary/type",
                 "salary/compilation"],
        "description": "Salary transactions and payslips",
    },
    "project": {
        "file": "project.md",
        "tags": ["project", "project/participant", "project/projectActivity",
                 "project/category", "project/hourlyRates"],
        "description": "Create and manage projects",
    },
    "company": {
        "file": "company.md",
        "tags": ["company"],
        "description": "Update company settings (singleton)",
    },
}


def load_spec():
    with open(SPEC_PATH, "r") as f:
        return json.load(f)


def load_overrides():
    if os.path.exists(OVERRIDES_PATH):
        with open(OVERRIDES_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    return {}


def load_status():
    if os.path.exists(STATUS_PATH):
        with open(STATUS_PATH, "r") as f:
            return json.load(f)
    return {"completed": [], "pending": list(CATEGORY_MAP.keys())}


def save_status(status):
    with open(STATUS_PATH, "w") as f:
        json.dump(status, f, indent=2)


def resolve_ref(spec, ref):
    """Resolve a $ref to the actual schema dict."""
    if not ref or not ref.startswith("#/"):
        return {}
    parts = ref.lstrip("#/").split("/")
    obj = spec
    for p in parts:
        obj = obj.get(p, {})
    return obj


def schema_name(ref):
    """Extract name from $ref like '#/components/schemas/Employee'."""
    return ref.split("/")[-1] if ref else ""


def get_writable_properties(spec, schema, depth=0):
    """
    Extract writable (non-readOnly) properties from a schema.
    Returns list of (name, type_str, required, description, extras) tuples.
    depth limits recursion for nested objects.
    """
    if "$ref" in schema:
        schema = resolve_ref(spec, schema["$ref"])

    if "allOf" in schema:
        merged_props = {}
        merged_required = set()
        for sub in schema["allOf"]:
            resolved = sub
            if "$ref" in sub:
                resolved = resolve_ref(spec, sub["$ref"])
            merged_props.update(resolved.get("properties", {}))
            merged_required.update(resolved.get("required", []))
        schema = {"properties": merged_props, "required": list(merged_required)}

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    results = []

    for name, prop in sorted(properties.items()):
        # Resolve ref for property
        actual_prop = prop
        ref_name = ""
        if "$ref" in prop:
            ref_name = schema_name(prop["$ref"])
            actual_prop = resolve_ref(spec, prop["$ref"])

        # Skip readOnly
        if actual_prop.get("readOnly", False):
            continue

        # Determine type
        prop_type = actual_prop.get("type", "")
        prop_format = actual_prop.get("format", "")
        is_required = name in required

        extras = {}

        if ref_name and not ref_name.startswith(("ListResponse", "ResponseWrapper")):
            type_str = f"ref({ref_name})"
            # For object references, get their writable props too (1 level)
            if depth < 1:
                sub_props = get_writable_properties(spec, actual_prop, depth + 1)
                if sub_props:
                    extras["sub_properties"] = sub_props
        elif prop_type == "array":
            items = actual_prop.get("items", {})
            if "$ref" in items:
                item_name = schema_name(items["$ref"])
                type_str = f"array({item_name})"
                if depth < 1:
                    item_schema = resolve_ref(spec, items["$ref"])
                    sub_props = get_writable_properties(spec, item_schema, depth + 1)
                    if sub_props:
                        extras["items_properties"] = sub_props
            else:
                item_type = items.get("type", "any")
                type_str = f"array({item_type})"
        elif prop_format:
            type_str = f"{prop_type}({prop_format})"
        else:
            type_str = prop_type or "any"

        # Enum values
        enum = actual_prop.get("enum", [])
        if enum:
            extras["enum"] = enum

        # Description
        desc = actual_prop.get("description", "").replace("\n", " ").strip()

        results.append((name, type_str, is_required, desc, extras))

    return results


def get_readonly_properties(spec, schema):
    """Extract readOnly property names from a schema."""
    if "$ref" in schema:
        schema = resolve_ref(spec, schema["$ref"])

    if "allOf" in schema:
        merged_props = {}
        for sub in schema["allOf"]:
            resolved = sub
            if "$ref" in sub:
                resolved = resolve_ref(spec, sub["$ref"])
            merged_props.update(resolved.get("properties", {}))
        schema = {"properties": merged_props}

    readonly = []
    for name, prop in sorted(schema.get("properties", {}).items()):
        actual = prop
        if "$ref" in prop:
            actual = resolve_ref(spec, prop["$ref"])
        if actual.get("readOnly", False):
            readonly.append(name)
    return readonly


def get_endpoints_for_category(spec, category_key):
    """Get all operations matching a category's tags or explicit paths."""
    cat = CATEGORY_MAP[category_key]
    tags = set(cat.get("tags", []))
    explicit_paths = set(cat.get("paths", []))
    ops = []

    for path, path_item in spec.get("paths", {}).items():
        for method in ["get", "post", "put", "delete", "patch"]:
            if method not in path_item:
                continue
            op = path_item[method]
            op_tags = set(op.get("tags", []))

            # Match by tag or explicit path
            if (tags and op_tags & tags) or (path in explicit_paths):
                ops.append({
                    "method": method.upper(),
                    "path": path,
                    "operation": op,
                    "tags": list(op_tags),
                })

    return ops


def format_send_exactly(spec, writable_props, depth=0):
    """Format writable properties as a JSON-like 'Send Exactly' block."""
    indent = "  " * (depth + 1)
    lines = []

    for name, type_str, is_req, desc, extras in writable_props:
        if type_str.startswith("ref("):
            lines.append(f'{indent}"{name}": {{"id": <int>}}')
        elif type_str.startswith("array(") and "items_properties" in extras:
            # Array of objects
            item_lines = []
            for sub_name, sub_type, sub_req, sub_desc, sub_extras in extras["items_properties"]:
                if sub_type.startswith("ref("):
                    item_lines.append(f'{indent}    "{sub_name}": {{"id": <int>}}')
                elif "enum" in sub_extras:
                    item_lines.append(f'{indent}    "{sub_name}": "{sub_extras["enum"][0]}"')
                elif sub_type.startswith("string"):
                    item_lines.append(f'{indent}    "{sub_name}": "<string>"')
                elif sub_type in ("number", "integer", "int32", "int64"):
                    item_lines.append(f'{indent}    "{sub_name}": <number>')
                elif sub_type.startswith("number") or sub_type.startswith("integer"):
                    item_lines.append(f'{indent}    "{sub_name}": <number>')
                elif sub_type == "boolean":
                    item_lines.append(f'{indent}    "{sub_name}": <boolean>')
                else:
                    item_lines.append(f'{indent}    "{sub_name}": <{sub_type}>')
            lines.append(f'{indent}"{name}": [\n{indent}  {{\n' +
                        ",\n".join(item_lines) +
                        f'\n{indent}  }}\n{indent}]')
        elif "enum" in extras:
            lines.append(f'{indent}"{name}": "{extras["enum"][0]}"')
        elif type_str.startswith("string"):
            if "date" in type_str:
                lines.append(f'{indent}"{name}": "YYYY-MM-DD"')
            else:
                lines.append(f'{indent}"{name}": "<string>"')
        elif type_str in ("number", "integer") or type_str.startswith("number") or type_str.startswith("integer"):
            lines.append(f'{indent}"{name}": <number>')
        elif type_str == "boolean":
            lines.append(f'{indent}"{name}": <boolean>')
        else:
            lines.append(f'{indent}"{name}": <{type_str}>')

    return "{\n" + ",\n".join(lines) + "\n}"


def generate_category(spec, overrides, category_key):
    """Generate the cheat sheet for one category."""
    cat = CATEGORY_MAP[category_key]
    ops = get_endpoints_for_category(spec, category_key)
    cat_overrides = overrides.get(category_key, {})

    lines = [f"# {cat['description']}\n"]

    # Category-level notes from overrides
    if cat_overrides.get("notes"):
        for note in cat_overrides["notes"]:
            lines.append(f"> **NOTE:** {note}\n")

    for op_info in sorted(ops, key=lambda x: (x["path"], x["method"])):
        method = op_info["method"]
        path = op_info["path"]
        operation = op_info["operation"]
        op_key = f"{method} {path}"

        summary = operation.get("summary", "").strip()
        deprecated = operation.get("deprecated", False)
        op_overrides = cat_overrides.get(op_key, {})

        # Header
        dep_str = " ⚠️ DEPRECATED" if deprecated else ""
        lines.append(f"## {method} {path}{dep_str}")
        if summary:
            lines.append(f"{summary}\n")

        # Prerequisites from overrides
        prereqs = op_overrides.get("prerequisites", [])
        if prereqs:
            lines.append("### Prerequisites")
            for p in prereqs:
                lines.append(f"- {p}")
            lines.append("")

        # Parameters
        params = operation.get("parameters", [])
        path_params = [p for p in params if p.get("in") == "path"]
        query_params = [p for p in params if p.get("in") == "query"]

        if path_params:
            lines.append("### Path Parameters")
            for p in path_params:
                ptype = p.get("schema", {}).get("type", "string")
                req = " **(required)**" if p.get("required") else ""
                lines.append(f"- `{p['name']}`: {ptype}{req}")
            lines.append("")

        if query_params:
            lines.append("### Query Parameters")
            lines.append("| Param | Type | Required | Description |")
            lines.append("|-------|------|----------|-------------|")
            for p in query_params:
                pschema = p.get("schema", {})
                ptype = pschema.get("type", "string")
                pfmt = pschema.get("format", "")
                if pfmt:
                    ptype = f"{ptype}({pfmt})"
                req = "yes" if p.get("required") else "no"
                desc = p.get("description", "").replace("\n", " ").strip()[:100]
                lines.append(f"| `{p['name']}` | {ptype} | {req} | {desc} |")
            lines.append("")

        # Request body
        rb = operation.get("requestBody", {})
        content = rb.get("content", {})
        body_schema = None
        content_type = None

        for ct in ["application/json", "application/json; charset=utf-8"]:
            if ct in content:
                body_schema = content[ct].get("schema", {})
                content_type = ct
                break

        if not body_schema and "multipart/form-data" in content:
            body_schema = content["multipart/form-data"].get("schema", {})
            content_type = "multipart/form-data"

        if body_schema:
            # Check if it's an array (bulk endpoint)
            is_array = body_schema.get("type") == "array"
            actual_schema = body_schema
            if is_array:
                actual_schema = body_schema.get("items", {})

            writable = get_writable_properties(spec, actual_schema)
            readonly = get_readonly_properties(spec, actual_schema)

            if writable:
                # Check for curated send_exactly override
                send_exactly_override = op_overrides.get("send_exactly")

                lines.append("### Send Exactly")
                if is_array:
                    lines.append("*Body is an array — wrap in `[...]` for bulk create.*\n")

                if send_exactly_override:
                    # Use the curated JSON example — this is the tested, correct body
                    lines.append(f"```json\n{send_exactly_override}\n```\n")
                    # All writable fields go to optional since we have a curated body
                    optional_props = writable
                else:
                    # Fall back to spec-derived required/optional split
                    required_props = [(n, t, r, d, e) for n, t, r, d, e in writable if r]
                    optional_props = [(n, t, r, d, e) for n, t, r, d, e in writable if not r]

                    if required_props:
                        send_json = format_send_exactly(spec, required_props)
                        if is_array:
                            send_json = f"[\n  {send_json}\n]"
                        lines.append(f"```json\n{send_json}\n```\n")
                    else:
                        # No required fields and no override — show note
                        important = writable[:8]
                        send_json = format_send_exactly(spec, important)
                        lines.append(f"*No fields explicitly marked required. Common fields:*\n")
                        lines.append(f"```json\n{send_json}\n```\n")

                if optional_props:
                    lines.append("### Optional Fields")
                    lines.append("| Field | Type | Description |")
                    lines.append("|-------|------|-------------|")
                    for name, type_str, _, desc, extras in optional_props:
                        enum_str = ""
                        if "enum" in extras:
                            vals = ", ".join(str(e) for e in extras["enum"][:6])
                            if len(extras["enum"]) > 6:
                                vals += ", ..."
                            enum_str = f" Enum: `{vals}`"
                        short_desc = (desc[:80] + "...") if len(desc) > 80 else desc
                        lines.append(f"| `{name}` | {type_str} | {short_desc}{enum_str} |")
                    lines.append("")

            # DO NOT SEND section
            # If there's a curated send_exactly, extract field names from it
            # to exclude from DO NOT SEND (they may be readOnly in spec but
            # needed on POST to establish relationships)
            send_exactly_fields = set()
            if send_exactly_override:
                import re as _re
                send_exactly_fields = set(_re.findall(r'"(\w+)":', send_exactly_override))

            do_not_send = []
            for ro_field in readonly:
                if ro_field in send_exactly_fields:
                    continue  # Field is in Send Exactly — don't contradict
                do_not_send.append(f"- `{ro_field}` (read-only)")

            # Add override-based DO NOT SEND
            extra_dns = op_overrides.get("do_not_send", [])
            for dns in extra_dns:
                if isinstance(dns, dict):
                    do_not_send.append(f"- `{dns['field']}` — {dns['reason']}")
                else:
                    do_not_send.append(f"- {dns}")

            if do_not_send:
                lines.append("### DO NOT SEND")
                lines.extend(do_not_send)
                lines.append("")

        # Response info
        for code in ["200", "201"]:
            resp = operation.get("responses", {}).get(code, {})
            resp_content = resp.get("content", {})
            for ct in ["application/json", "*/*"]:
                if ct in resp_content:
                    resp_schema = resp_content[ct].get("schema", {})
                    if "$ref" in resp_schema:
                        rname = schema_name(resp_schema["$ref"])
                        if rname.startswith("ResponseWrapper"):
                            lines.append(f"### Response\n`{{value: {{...}}}}` — single object wrapped.\n")
                        elif rname.startswith("ListResponse"):
                            lines.append(f"### Response\n`{{fullResultSize, from, count, values: [...]}}` — paginated list.\n")
                        else:
                            lines.append(f"### Response\n`{rname}`\n")
                    break
            break

        # Response capture from overrides
        captures = op_overrides.get("response_capture", [])
        if captures:
            lines.append("**Capture for next steps:**")
            for c in captures:
                lines.append(f"- `{c}`")
            lines.append("")

        # Common errors from overrides
        errors = op_overrides.get("common_errors", [])
        if errors:
            lines.append("### Common Errors")
            lines.append("| Symptom | Fix |")
            lines.append("|---------|-----|")
            for err in errors:
                lines.append(f"| {err['symptom']} | {err['fix']} |")
            lines.append("")

        # Extra notes from overrides
        notes = op_overrides.get("notes", [])
        if notes:
            for note in notes:
                lines.append(f"> ⚠️ {note}\n")

        lines.append("---\n")

    return "\n".join(lines)


def generate_one(category_key):
    """Generate a single category and update status."""
    spec = load_spec()
    overrides = load_overrides()
    status = load_status()

    print(f"Generating: {category_key} → endpoints/{CATEGORY_MAP[category_key]['file']}")

    content = generate_category(spec, overrides, category_key)
    out_path = os.path.join(ENDPOINTS_DIR, CATEGORY_MAP[category_key]["file"])
    os.makedirs(ENDPOINTS_DIR, exist_ok=True)

    with open(out_path, "w") as f:
        f.write(content)

    # Update status
    if category_key not in status["completed"]:
        status["completed"].append(category_key)
    if category_key in status["pending"]:
        status["pending"].remove(category_key)
    save_status(status)

    print(f"  ✓ Written to {out_path}")
    return out_path


def generate_all():
    """Generate all categories."""
    for key in CATEGORY_MAP:
        generate_one(key)


def show_status():
    """Show generation progress."""
    status = load_status()
    total = len(CATEGORY_MAP)
    done = len(status["completed"])
    print(f"Progress: {done}/{total} categories generated\n")
    print("Completed:")
    for k in status["completed"]:
        print(f"  ✓ {k} → endpoints/{CATEGORY_MAP[k]['file']}")
    print("\nPending:")
    for k in status["pending"]:
        print(f"  ○ {k} → endpoints/{CATEGORY_MAP[k]['file']}")


def next_pending():
    """Return the next pending category, or None."""
    status = load_status()
    return status["pending"][0] if status["pending"] else None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--list":
            for key, cat in sorted(CATEGORY_MAP.items()):
                print(f"  {key:25s} → endpoints/{cat['file']:30s} {cat['description']}")
        elif arg == "--status":
            show_status()
        elif arg == "--next":
            nxt = next_pending()
            if nxt:
                generate_one(nxt)
            else:
                print("All categories generated!")
        elif arg in CATEGORY_MAP:
            generate_one(arg)
        else:
            print(f"Unknown category: {arg}")
            print(f"Available: {', '.join(sorted(CATEGORY_MAP.keys()))}")
            sys.exit(1)
    else:
        generate_all()
