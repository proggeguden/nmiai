"""Parse swagger.json and generate typed LangChain tools for Tripletex API."""

import json
import re
from typing import Any, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

# Fields that are read-only or server-generated — skip in tool args
READONLY_FIELDS = frozenset({
    "id", "version", "changes", "url", "displayName", "companyId",
    "systemGenerated", "isDeletable", "isProxy",
})

# Fields to skip because sending them alongside related fields causes 422 validation errors.
# e.g. Tripletex auto-calculates priceIncludingVatCurrency from priceExcludingVatCurrency;
# sending both (with the incl. one defaulting to 0) triggers a mismatch error.
SKIP_FIELDS = frozenset({
    "priceIncludingVatCurrency",
})

# Curated allowlist: (path, method) -> tool_name
ENDPOINT_ALLOWLIST: list[tuple[str, str, str]] = [
    # Employee
    ("/employee", "get", "search_employees"),
    ("/employee", "post", "create_employee"),
    ("/employee/{id}", "get", "get_employee"),
    ("/employee/{id}", "put", "update_employee"),
    # Customer
    ("/customer", "get", "search_customers"),
    ("/customer", "post", "create_customer"),
    ("/customer/{id}", "get", "get_customer"),
    ("/customer/{id}", "put", "update_customer"),
    ("/customer/{id}", "delete", "delete_customer"),
    # Product
    ("/product", "get", "search_products"),
    ("/product", "post", "create_product"),
    ("/product/{id}", "get", "get_product"),
    ("/product/{id}", "put", "update_product"),
    ("/product/{id}", "delete", "delete_product"),
    # Order
    ("/order", "get", "search_orders"),
    ("/order", "post", "create_order"),
    ("/order/{id}", "get", "get_order"),
    ("/order/{id}", "put", "update_order"),
    ("/order/{id}", "delete", "delete_order"),
    ("/order/orderline", "post", "create_order_line"),
    # Invoice
    ("/invoice", "get", "search_invoices"),
    ("/invoice", "post", "create_invoice"),
    ("/invoice/{id}", "get", "get_invoice"),
    # TravelExpense
    ("/travelExpense", "get", "search_travel_expenses"),
    ("/travelExpense", "post", "create_travel_expense"),
    ("/travelExpense/{id}", "get", "get_travel_expense"),
    ("/travelExpense/{id}", "put", "update_travel_expense"),
    ("/travelExpense/{id}", "delete", "delete_travel_expense"),
    # Project
    ("/project", "get", "search_projects"),
    ("/project", "post", "create_project"),
    ("/project/{id}", "get", "get_project"),
    ("/project/{id}", "put", "update_project"),
    ("/project/{id}", "delete", "delete_project"),
    # Department
    ("/department", "get", "search_departments"),
    ("/department", "post", "create_department"),
    ("/department/{id}", "get", "get_department"),
    ("/department/{id}", "put", "update_department"),
    ("/department/{id}", "delete", "delete_department"),
    # Ledger voucher
    ("/ledger/voucher", "get", "search_vouchers"),
    ("/ledger/voucher", "post", "create_voucher"),
]

# Manually curated descriptions for the most common tools
TOOL_DESCRIPTIONS: dict[str, str] = {
    "search_employees": "Search employees. Use query params: firstName, lastName, email, fields (e.g. 'id,firstName,lastName'). Returns {values: [...]}.",
    "create_employee": "Create an employee. Required: first_name, last_name. user_type defaults to 'STANDARD'; set to 'EXTENDED' for admin access.",
    "get_employee": "Get employee by ID. Use fields param to select specific fields.",
    "update_employee": "Update employee by ID. Include version from GET response. Only send changed fields + version.",
    "search_customers": "Search customers. Use query params: name, email, fields. Returns {values: [...]}.",
    "create_customer": "Create a customer. Required: name. Set isCustomer=true.",
    "get_customer": "Get customer by ID.",
    "update_customer": "Update customer by ID. Include version from GET response.",
    "delete_customer": "Delete customer by ID.",
    "search_products": "Search products. Use query params: name, number, fields. Returns {values: [...]}.",
    "create_product": "Create a product. Include name and priceExcludingVatCurrency.",
    "get_product": "Get product by ID.",
    "update_product": "Update product by ID. Include version.",
    "delete_product": "Delete product by ID.",
    "search_orders": "Search orders. Use query params: orderDateFrom, orderDateTo, customerId, fields. Returns {values: [...]}.",
    "create_order": "Create an order. Required: customer_id, orderDate, deliveryDate. Include order_lines as JSON array.",
    "get_order": "Get order by ID.",
    "update_order": "Update order by ID. Include version.",
    "delete_order": "Delete order by ID.",
    "create_order_line": "Add an order line to an existing order. Required: order_id, description or product.",
    "search_invoices": "Search invoices. Required: invoiceDateFrom, invoiceDateTo. Returns {values: [...]}.",
    "create_invoice": "Create an invoice from an order. Required: invoiceDate, invoiceDueDate, order_ids (list of order IDs).",
    "get_invoice": "Get invoice by ID.",
    "search_travel_expenses": "Search travel expenses. Returns {values: [...]}.",
    "create_travel_expense": "Create a travel expense. Required: employee_id. Use travel_details_* fields for dates/route.",
    "get_travel_expense": "Get travel expense by ID.",
    "update_travel_expense": "Update travel expense by ID. Include version.",
    "delete_travel_expense": "Delete travel expense by ID.",
    "search_projects": "Search projects. Use query params: name, fields. Returns {values: [...]}.",
    "create_project": "Create a project. Required: name, project_manager_id (employee ID), startDate.",
    "get_project": "Get project by ID.",
    "update_project": "Update project by ID. Include version.",
    "delete_project": "Delete project by ID.",
    "search_departments": "Search departments. Use query params: name, fields. Returns {values: [...]}.",
    "create_department": "Create a department. Required: name.",
    "get_department": "Get department by ID.",
    "update_department": "Update department by ID. Include version.",
    "delete_department": "Delete department by ID.",
    "search_vouchers": "Search ledger vouchers. Use dateFrom, dateTo. Returns {values: [...]}.",
    "create_voucher": "Create a ledger voucher. Required: date. NOTE: vouchers also need 'postings' which is not yet supported as a flat arg — use the raw body for complex vouchers.",
}

# Nested $ref fields that should be flattened to _id args
# Maps: schema_name -> { field_name -> ref_schema_name }
REF_FIELDS_TO_FLATTEN = {
    "Employee": {"phoneNumberMobileCountry": "Country", "internationalId": "InternationalId", "address": "Address"},
    "Customer": {"deliveryAddress": "DeliveryAddress", "postalAddress": "Address", "physicalAddress": "Address", "category1": "CustomerCategory", "category2": "CustomerCategory", "category3": "CustomerCategory", "accountManager": "Employee"},
    "Order": {"customer": "Customer", "contact": "Contact", "attn": "Contact", "ourContact": "Contact", "ourContactEmployee": "Employee", "department": "Department", "project": "Project", "currency": "Currency", "deliveryAddress": "DeliveryAddress"},
    "Invoice": {},
    "TravelExpense": {"employee": "Employee", "project": "Project", "department": "Department", "travelDetails": "TravelDetails"},
    "Project": {"projectManager": "Employee", "customer": "Customer", "department": "Department", "mainProject": "Project"},
    "Department": {"departmentManager": "Employee"},
}

# TravelDetails sub-fields that get flattened with travel_details_ prefix
TRAVEL_DETAILS_FIELDS = [
    ("departureDate", str, "Departure date (YYYY-MM-DD)"),
    ("returnDate", str, "Return date (YYYY-MM-DD)"),
    ("departureFrom", str, "Departure location"),
    ("destination", str, "Destination"),
    ("purpose", str, "Purpose of travel"),
    ("isDayTrip", bool, "Whether this is a day trip"),
    ("isForeignTravel", bool, "Whether this is foreign travel"),
    ("departureTime", str, "Departure time"),
    ("returnTime", str, "Return time"),
]


# ────────────────────────────────────────────────────────────────────────────
# Pre-call validation: required fields, type coercion, defaults
# The swagger spec says required=[] for everything, but the API actually
# enforces these at runtime. We encode what we've learned here.
# ────────────────────────────────────────────────────────────────────────────

# tool_name -> list of (field_name, default_value_or_None)
#   default=None means "required, no default — return error if missing"
REQUIRED_FIELDS: dict[str, list[tuple[str, Any]]] = {
    "create_employee": [
        ("first_name", None),
        ("last_name", None),
        ("user_type", "STANDARD"),  # API rejects null userType
    ],
    "create_customer": [
        ("name", None),
        ("is_customer", True),
    ],
    "create_product": [
        ("name", None),
    ],
    "create_order": [
        ("customer_id", None),
        ("order_date", None),
        ("delivery_date", None),
    ],
    "create_order_line": [
        ("order_id", None),
    ],
    "create_invoice": [
        ("invoice_date", None),
        ("invoice_due_date", None),
        ("order_ids", None),
    ],
    "create_travel_expense": [
        ("employee_id", None),
    ],
    "create_project": [
        ("name", None),
        ("project_manager_id", None),
        ("start_date", None),
    ],
    "create_department": [
        ("name", None),
    ],
    "create_voucher": [
        ("date", None),
    ],
}

# Fields that should be coerced to specific types
# tool_name -> field_name -> target_type
TYPE_COERCIONS: dict[str, dict[str, type]] = {
    "create_product": {
        "price_excluding_vat_currency": float,
        "cost_excluding_vat_currency": float,
    },
    "create_order": {
        "customer_id": int,
    },
    "create_order_line": {
        "order_id": int,
        "count": float,
        "unit_price_excluding_vat_currency": float,
        "product_id": int,
    },
    "create_invoice": {
        # order_ids is a comma-separated string — validated in _rebuild_body
    },
    "create_travel_expense": {
        "employee_id": int,
        "project_id": int,
        "department_id": int,
    },
    "create_project": {
        "project_manager_id": int,
        "customer_id": int,
        "department_id": int,
    },
    "create_employee": {
        "department_id": int,
    },
    "create_customer": {
        "account_manager_id": int,
    },
}


def validate_and_fix(tool_name: str, args: dict) -> tuple[dict, list[str]]:
    """Validate tool args before API call. Returns (fixed_args, errors).

    - Fills defaults for required fields when possible
    - Coerces types (str "1500" -> float 1500.0)
    - Returns error strings for unfixable issues (caller returns them as tool result)
    """
    args = dict(args)  # don't mutate the original
    errors = []

    # 1. Check required fields, fill defaults
    for field, default in REQUIRED_FIELDS.get(tool_name, []):
        val = args.get(field)
        if val is None or val == "":
            if default is not None:
                args[field] = default
            else:
                errors.append(f"Required field '{field}' is missing.")

    # 2. Type coercions
    for field, target_type in TYPE_COERCIONS.get(tool_name, {}).items():
        val = args.get(field)
        if val is not None and not isinstance(val, target_type):
            try:
                args[field] = target_type(val)
            except (ValueError, TypeError):
                errors.append(f"Field '{field}' must be {target_type.__name__}, got {type(val).__name__}: {val}")

    # 3. Boolean coercion for any field that looks boolean
    for field, val in args.items():
        if isinstance(val, str) and val.lower() in ("true", "false"):
            args[field] = val.lower() == "true"

    return args, errors


def _resolve_ref(spec: dict, ref: str) -> dict:
    """Resolve a $ref string to its schema dict."""
    parts = ref.replace("#/", "").split("/")
    obj = spec
    for p in parts:
        obj = obj[p]
    return obj


def _get_schema_name(spec: dict, path: str, method: str) -> Optional[str]:
    """Extract the schema name from a request body or response."""
    op = spec["paths"][path][method]

    # For POST/PUT, look at requestBody
    if method in ("post", "put"):
        rb = op.get("requestBody", {})
        content = rb.get("content", {})
        for ct, schema_info in content.items():
            ref = schema_info.get("schema", {}).get("$ref", "")
            if ref:
                return ref.split("/")[-1]

    # For GET/DELETE, look at 200 response
    resp = op.get("responses", {}).get("200", {})
    content = resp.get("content", {})
    for ct, schema_info in content.items():
        ref = schema_info.get("schema", {}).get("$ref", "")
        if ref:
            # Could be ListResponse or ResponseWrapper
            name = ref.split("/")[-1]
            # Strip ListResponse/ResponseWrapper prefix
            for prefix in ("ListResponse", "ResponseWrapper"):
                if name.startswith(prefix):
                    return name[len(prefix):]
            return name
    return None


def _get_query_params(spec: dict, path: str, method: str) -> list[dict]:
    """Get query parameters for a GET endpoint."""
    op = spec["paths"][path][method]
    return [p for p in op.get("parameters", []) if p.get("in") == "query"]


def _build_get_tool(
    spec: dict, path: str, tool_name: str, description: str, make_request_fn
) -> StructuredTool:
    """Build a tool for GET endpoints with query params."""
    query_params = _get_query_params(spec, path, "get")
    has_id = "{id}" in path

    # Build Pydantic fields
    fields = {}
    if has_id:
        fields["id"] = (int, Field(description="Resource ID"))

    # Add useful query params
    for p in query_params:
        pname = p["name"]
        ptype = p.get("schema", {}).get("type", "string")
        py_type = {"integer": int, "boolean": bool, "number": float}.get(ptype, str)
        fields[pname] = (Optional[py_type], Field(default=None, description=p.get("description", "")))

    model = create_model(f"{tool_name}_args", **fields)

    def _run(**kwargs):
        params = {}
        resource_id = kwargs.pop("id", None)

        for k, v in kwargs.items():
            if v is not None:
                params[k] = v

        endpoint = path.replace("{id}", str(resource_id)) if resource_id else path
        return make_request_fn("GET", endpoint, params=params)

    return StructuredTool.from_function(
        func=_run,
        name=tool_name,
        description=description,
        args_schema=model,
    )


def _build_delete_tool(
    path: str, tool_name: str, description: str, make_request_fn
) -> StructuredTool:
    """Build a tool for DELETE endpoints."""
    fields = {"id": (int, Field(description="Resource ID to delete"))}
    model = create_model(f"{tool_name}_args", **fields)

    def _run(id: int):
        endpoint = path.replace("{id}", str(id))
        return make_request_fn("DELETE", endpoint)

    return StructuredTool.from_function(
        func=_run,
        name=tool_name,
        description=description,
        args_schema=model,
    )


def _build_body_tool(
    spec: dict, path: str, method: str, tool_name: str, description: str, make_request_fn
) -> StructuredTool:
    """Build a tool for POST/PUT endpoints with request body."""
    schema_name = _get_schema_name(spec, path, method)
    has_id = "{id}" in path

    fields = {}
    nested_rebuilders = {}  # field_name -> how to rebuild nested object

    if has_id:
        fields["id"] = (int, Field(description="Resource ID"))

    if schema_name and schema_name in spec.get("components", {}).get("schemas", {}):
        schema = spec["components"]["schemas"][schema_name]
        props = schema.get("properties", {})
        ref_map = REF_FIELDS_TO_FLATTEN.get(schema_name, {})

        for prop_name, prop_def in props.items():
            if prop_name in READONLY_FIELDS or prop_name in SKIP_FIELDS:
                continue
            if prop_def.get("readOnly"):
                continue

            ref = prop_def.get("$ref", "")

            # Handle special nested objects
            if prop_name == "travelDetails" and schema_name == "TravelExpense":
                # Flatten travelDetails into travel_details_* fields
                for td_field, td_type, td_desc in TRAVEL_DETAILS_FIELDS:
                    flat_name = f"travel_details_{_camel_to_snake(td_field)}"
                    fields[flat_name] = (Optional[td_type], Field(default=None, description=td_desc))
                nested_rebuilders["travelDetails"] = "travel_details"
                continue

            if prop_name == "orderLines" and schema_name == "Order":
                # Accept order_lines as a JSON string (list of dicts)
                fields["order_lines"] = (Optional[str], Field(
                    default=None,
                    description='Order lines as JSON array. Each item: {"description": "...", "count": 1.0, "unitPriceExcludingVatCurrency": 100.0}'
                ))
                nested_rebuilders["orderLines"] = "order_lines_json"
                continue

            if ref and prop_name in ref_map:
                # Flatten ref to _id field
                flat_name = f"{_camel_to_snake(prop_name)}_id"
                fields[flat_name] = (Optional[int], Field(
                    default=None,
                    description=f"ID of the {ref_map[prop_name]} to link"
                ))
                nested_rebuilders[prop_name] = ("ref_id", flat_name)
                continue

            if ref:
                # Skip complex refs we don't flatten
                continue

            # Handle arrays we don't specifically handle
            if prop_def.get("type") == "array":
                # Special case: orders in Invoice
                if prop_name == "orders" and schema_name == "Invoice":
                    fields["order_ids"] = (Optional[str], Field(
                        default=None,
                        description="Comma-separated order IDs for this invoice"
                    ))
                    nested_rebuilders["orders"] = "order_ids_list"
                    continue
                # Skip other arrays
                continue

            # Simple scalar field
            py_type = _swagger_type_to_python(prop_def)
            snake_name = _camel_to_snake(prop_name)

            # For PUT, version is important
            if prop_name == "version":
                fields["version"] = (Optional[int], Field(default=None, description="Object version (required for PUT to prevent conflicts)"))
                continue

            fields[snake_name] = (Optional[py_type], Field(
                default=None,
                description=prop_def.get("description", ""),
                **({"json_schema_extra": {"enum": prop_def["enum"]}} if "enum" in prop_def else {})
            ))

    # Special: create_order_line needs order_id
    if tool_name == "create_order_line":
        fields["order_id"] = (int, Field(description="ID of the order to add line to"))
        fields["description"] = (Optional[str], Field(default=None, description="Line description"))
        fields["count"] = (Optional[float], Field(default=None, description="Quantity"))
        fields["unit_price_excluding_vat_currency"] = (Optional[float], Field(default=None, description="Unit price excl. VAT"))
        fields["product_id"] = (Optional[int], Field(default=None, description="Product ID"))
        nested_rebuilders = {"_order_line": True}

    # Special: create_invoice needs order_ids
    if tool_name == "create_invoice" and "order_ids" not in fields:
        fields["order_ids"] = (Optional[str], Field(
            default=None,
            description="Comma-separated order IDs for this invoice"
        ))

    model = create_model(f"{tool_name}_args", **fields)

    def _make_run(p, m, nr, sn, tn):
        def _run(**kwargs):
            resource_id = kwargs.pop("id", None)
            # Validate and fix args before calling API
            kwargs, validation_errors = validate_and_fix(tn, kwargs)
            if validation_errors:
                return json.dumps({
                    "status": 400,
                    "message": "Pre-call validation failed",
                    "validationMessages": [{"field": e.split("'")[1] if "'" in e else "", "message": e} for e in validation_errors],
                })
            body = _rebuild_body(kwargs, nr, sn)
            if isinstance(body, str):  # _rebuild_body returns error string on failure
                return json.dumps({"status": 400, "message": body})
            endpoint = p.replace("{id}", str(resource_id)) if resource_id else p
            return make_request_fn(m.upper(), endpoint, body=body)
        return _run

    return StructuredTool.from_function(
        func=_make_run(path, method, nested_rebuilders, schema_name, tool_name),
        name=tool_name,
        description=description,
        args_schema=model,
    )


def _rebuild_body(kwargs: dict, nested_rebuilders: dict, schema_name: Optional[str]) -> dict:
    """Reconstruct the API request body from flat tool args."""
    body = {}

    # Handle order line special case
    if "_order_line" in nested_rebuilders:
        order_id = kwargs.pop("order_id", None)
        body["order"] = {"id": order_id}
        if kwargs.get("description"):
            body["description"] = kwargs["description"]
        if kwargs.get("count") is not None:
            body["count"] = kwargs["count"]
        if kwargs.get("unit_price_excluding_vat_currency") is not None:
            body["unitPriceExcludingVatCurrency"] = kwargs["unit_price_excluding_vat_currency"]
        if kwargs.get("product_id"):
            body["product"] = {"id": kwargs["product_id"]}
        return body

    for key, value in kwargs.items():
        if value is None:
            continue

        # Check if this is a flattened ref field (_id suffix)
        handled = False
        for orig_name, rebuilder in nested_rebuilders.items():
            if isinstance(rebuilder, tuple) and rebuilder[0] == "ref_id" and rebuilder[1] == key:
                body[orig_name] = {"id": value}
                handled = True
                break

        if handled:
            continue

        # Handle travel_details_ prefix
        if key.startswith("travel_details_") and "travelDetails" in nested_rebuilders:
            if "travelDetails" not in body:
                body["travelDetails"] = {}
            td_key = _snake_to_camel(key.replace("travel_details_", ""))
            body["travelDetails"][td_key] = value
            continue

        # Handle order_lines JSON
        if key == "order_lines" and "orderLines" in nested_rebuilders:
            try:
                body["orderLines"] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return f"Error: order_lines must be valid JSON array"
            continue

        # Handle order_ids for invoice
        if key == "order_ids":
            try:
                ids = [int(x.strip()) for x in str(value).split(",")]
                body["orders"] = [{"id": oid} for oid in ids]
            except ValueError:
                return f"Error: order_ids must be comma-separated integers"
            continue

        # Regular field: convert snake_case back to camelCase
        camel_key = _snake_to_camel(key)
        body[camel_key] = value

    return body


def _camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case."""
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s1).lower()


def _snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase."""
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _swagger_type_to_python(prop_def: dict) -> type:
    """Map OpenAPI type to Python type."""
    t = prop_def.get("type", "string")
    fmt = prop_def.get("format", "")
    if t == "integer":
        return int
    if t == "number":
        return float
    if t == "boolean":
        return bool
    return str


def generate_tools(swagger_path: str, make_request_fn) -> list[StructuredTool]:
    """Parse swagger.json and generate typed tools.

    Args:
        swagger_path: Path to swagger.json
        make_request_fn: The _make_request function from tools.py

    Returns:
        List of StructuredTool instances
    """
    with open(swagger_path) as f:
        spec = json.load(f)

    tools = []
    for path, method, tool_name in ENDPOINT_ALLOWLIST:
        # Verify the endpoint exists in the spec
        if path not in spec.get("paths", {}):
            continue
        if method not in spec["paths"][path]:
            continue

        description = TOOL_DESCRIPTIONS.get(tool_name, f"{method.upper()} {path}")

        if method == "get":
            t = _build_get_tool(spec, path, tool_name, description, make_request_fn)
        elif method == "delete":
            t = _build_delete_tool(path, tool_name, description, make_request_fn)
        else:
            t = _build_body_tool(spec, path, method, tool_name, description, make_request_fn)

        tools.append(t)

    return tools


def get_tool_summaries(tools: list[StructuredTool]) -> str:
    """Generate a compact summary of all tools for the planner prompt."""
    lines = []
    for t in tools:
        # Get the field names from the schema
        schema = t.args_schema.model_json_schema() if t.args_schema else {}
        props = schema.get("properties", {})
        arg_parts = []
        for pname, pdef in props.items():
            ptype = pdef.get("type", "str")
            required = pname in schema.get("required", [])
            marker = " (required)" if required else ""
            arg_parts.append(f"{pname}: {ptype}{marker}")

        args_str = ", ".join(arg_parts) if arg_parts else "none"
        lines.append(f"- {t.name}: {t.description} Args: [{args_str}]")

    return "\n".join(lines)
