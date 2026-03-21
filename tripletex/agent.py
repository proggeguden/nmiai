"""LangGraph agent with planner/executor architecture for Tripletex."""

import json
import os
import re
from datetime import date
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph

from logger import get_logger
from prompts import (
    CHALLENGER_PROFILE,
    FIX_ARGS_PROMPT,
    PLANNER_PROMPT,
    PLANNER_PROFILE,
    REPLAN_PROMPT,
    VERIFY_PROMPT,
)
from state import AgentState
from tools import load_tools

log = get_logger("tripletex.agent")

# Sentinel for unresolved $step_N placeholders (empty search results, etc.)
_UNRESOLVED = "__UNRESOLVED__"

MAX_REPLANS = 3  # max replan attempts per invocation (FIX_ARGS → REPLAN → REPLAN)


def validate_plan(plan: list[dict]) -> list[dict]:
    """Validate and auto-fix plan steps against endpoint cards.

    Catches cheapest errors before they hit the API:
    - Merges consecutive same-path POSTs into bulk /list calls
    - Auto-injects paymentTypeId/invoiceDate for /:invoice steps
    - Adds missing required fields with defaults
    - Removes conflicting fields
    - Prepends GET /travelExpense/paymentType when plan has travel costs without paymentType
    - Validates enum values
    """
    try:
        from endpoint_catalog import ENDPOINT_CARDS
    except ImportError:
        return plan

    # ── A0: Merge consecutive same-path POSTs into bulk /list calls ──
    plan = _merge_consecutive_posts_to_list(plan, ENDPOINT_CARDS)

    # ── A1: Proactive bank account ensure for invoicing plans ──
    has_invoice_action = any(
        s.get("tool_name") == "call_api"
        and (
            "/:invoice" in s.get("args", {}).get("path", "")
            or (
                s.get("args", {}).get("method") == "POST"
                and s.get("args", {}).get("path") == "/invoice"
            )
        )
        for s in plan
    )
    if has_invoice_action:
        for step in plan:
            step["step_number"] += 1
            _shift_step_refs(step, offset=1)
        plan.insert(
            0,
            {
                "step_number": 1,
                "tool_name": "ensure_bank_account",
                "args": {},
                "description": "Ensure company bank account exists (required for invoicing)",
            },
        )
        log.info("Validation: prepended ensure_bank_account step for invoicing plan")

    # ── A2: Auto-inject division + link for employment plans ──
    # Employment must have a division. We inject: ensure_division meta-step before POST /employee/employment,
    # and add division:{id} to the employment body.
    has_employment = False
    employment_idx = None
    for i, step in enumerate(plan):
        if step.get("tool_name") != "call_api":
            continue
        args = step.get("args", {})
        if args.get("method") == "POST" and args.get("path") == "/employee/employment":
            has_employment = True
            employment_idx = i
            break

    if has_employment and employment_idx is not None:
        emp_step = plan[employment_idx]
        emp_body = emp_step.get("args", {}).get("body", {})
        # Only inject if division is not already in the body
        if isinstance(emp_body, dict) and "division" not in emp_body:
            # Insert ensure_division meta-step right before the employment step
            div_step_number = emp_step["step_number"]
            for step in plan[employment_idx:]:
                step["step_number"] += 1
                _shift_step_refs(step, offset=1, min_step=div_step_number)
            plan.insert(
                employment_idx,
                {
                    "step_number": div_step_number,
                    "tool_name": "ensure_division",
                    "args": {},
                    "description": "Ensure company division exists (required for employment)",
                },
            )
            # Add division ref to the employment body
            emp_body["division"] = {"id": f"$step_{div_step_number}.value.id"}
            log.info("Validation: prepended ensure_division step for employment plan")

    # (Travel paymentType injection removed — costs are now inlined in POST /travelExpense)

    # (A3 removed: vatType ID mapping was wrong — always let agent GET /ledger/vatType)

    # ── B4: Auto-inject department for POST /employee ──
    has_employee_post = False
    employee_post_idx = None
    has_department_in_plan = False
    for i, step in enumerate(plan):
        if step.get("tool_name") != "call_api":
            continue
        args = step.get("args", {})
        method = args.get("method", "")
        path = args.get("path", "")
        body = args.get("body", {})
        if method == "POST" and path == "/employee" and isinstance(body, dict):
            has_employee_post = True
            employee_post_idx = i
            if "department" in body:
                has_department_in_plan = True
        if method == "POST" and path == "/department":
            has_department_in_plan = True

    if (
        has_employee_post
        and not has_department_in_plan
        and employee_post_idx is not None
    ):
        # Prepend GET /department?count=1 before the employee POST
        dept_step_number = plan[employee_post_idx]["step_number"]
        dept_step = {
            "step_number": dept_step_number,
            "tool_name": "call_api",
            "args": {
                "method": "GET",
                "path": "/department",
                "query_params": {"count": 1, "fields": "id"},
            },
            "description": "Get department for employee (required)",
        }
        # Renumber from employee_post_idx onward (only shift refs >= insertion point)
        for step in plan[employee_post_idx:]:
            step["step_number"] += 1
            _shift_step_refs(step, offset=1, min_step=dept_step_number)
        plan.insert(employee_post_idx, dept_step)

        # Inject department ref into employee body
        emp_step = plan[employee_post_idx + 1]
        emp_body = emp_step.get("args", {}).get("body", {})
        if isinstance(emp_body, dict) and "department" not in emp_body:
            emp_body["department"] = {"id": f"$step_{dept_step_number}.values[0].id"}
        log.info(
            "Validation: injected GET /department step and department ref for POST /employee"
        )

    for step in plan:
        if step.get("tool_name") != "call_api":
            continue
        args = step.get("args", {})
        method = args.get("method", "")
        path = args.get("path", "")
        body = args.get("body", {})
        query_params = args.get("query_params", {})

        # ── B0: Strip /v2 prefix from paths (base URL already has /v2) ──
        if isinstance(path, str) and path.startswith("/v2/"):
            args["path"] = path[3:]
            path = args["path"]
            log.info("Validation: stripped /v2 prefix from path")

        # ── B0b: Strip vatType from order lines ONLY if it's a hardcoded wrong ID ──
        # Keep vatType if it references a $step_N lookup (planner looked it up correctly)
        # or uses a known valid ID. Only strip bare integer IDs that may be wrong mappings.
        if (
            method == "POST"
            and path in ("/order", "/order/list")
            and isinstance(body, (dict, list))
        ):
            bodies = body if isinstance(body, list) else [body]
            for b in bodies:
                if isinstance(b, dict):
                    for ol in b.get("orderLines", []):
                        if isinstance(ol, dict) and "vatType" in ol:
                            vat_ref = ol["vatType"]
                            # Keep if it's a $step_N reference (planner did a lookup)
                            if (
                                isinstance(vat_ref, dict)
                                and isinstance(vat_ref.get("id"), str)
                                and "$step_" in str(vat_ref.get("id", ""))
                            ):
                                continue
                            # Keep if it's a known valid OUTPUT vatType ID
                            # 3=25%, 31=15%(food), 32=12%(transport), 5=0%(exempt), 6=0%(exempt)
                            if isinstance(vat_ref, dict) and vat_ref.get("id") in (
                                3,
                                5,
                                6,
                                31,
                                32,
                            ):
                                continue
                            # Strip anything else (likely wrong hardcoded ID)
                            del ol["vatType"]
                            log.info(
                                "Validation: stripped unknown vatType from order line"
                            )

        # ── B0c: Auto-inject invoiceDueDate for POST /invoice ──
        if method == "POST" and path == "/invoice" and isinstance(body, dict):
            if "invoiceDueDate" not in body:
                from datetime import timedelta

                inv_date = body.get("invoiceDate", date.today().isoformat())
                try:
                    due = date.fromisoformat(inv_date) + timedelta(days=14)
                    body["invoiceDueDate"] = due.isoformat()
                except ValueError:
                    body["invoiceDueDate"] = date.today().isoformat()
                log.info("Validation: added missing invoiceDueDate to POST /invoice")

        # ── B1: Fix fields filter dot→parentheses ──
        if method == "GET" and isinstance(query_params, dict):
            fields_val = query_params.get("fields", "")
            if isinstance(fields_val, str) and "." in fields_val:
                # Convert e.g. "orders.orderLines.description" → "orders(orderLines(description))"
                fixed = _fix_fields_dots(fields_val)
                if fixed != fields_val:
                    query_params["fields"] = fixed
                    log.info(
                        f"Validation: fixed fields filter dots→parentheses: {fields_val} → {fixed}"
                    )

        # ── B2: Fix date range From < To ──
        if method == "GET" and isinstance(query_params, dict):
            _fix_date_range(query_params, "invoiceDateFrom", "invoiceDateTo")
            _fix_date_range(query_params, "dateFrom", "dateTo")
            _fix_date_range(query_params, "startDateFrom", "startDateTo")

        # ── B5: Strip projectManager $step ref from POST /project ──
        if method == "POST" and path == "/project" and isinstance(body, dict):
            pm = body.get("projectManager")
            if isinstance(pm, dict):
                pm_id = pm.get("id")
                if isinstance(pm_id, str) and "$step_" in pm_id:
                    # Keep it — the planner intended to use a created employee
                    # But log for monitoring
                    log.info(
                        f"Validation: POST /project has projectManager ref {pm_id}"
                    )

        # Quick fix: POST /project — add startDate if missing
        if method == "POST" and path == "/project" and isinstance(body, dict):
            if "startDate" not in body:
                body["startDate"] = date.today().isoformat()
                log.info("Validation: added missing startDate to POST /project")

        # Quick fix: POST /ledger/voucher — remove voucherType, fix null postings, add row numbers
        if method == "POST" and path == "/ledger/voucher" and isinstance(body, dict):
            if "voucherType" in body:
                del body["voucherType"]
                log.info("Validation: stripped voucherType from POST /ledger/voucher")
            # B3: Fix null postings
            if body.get("postings") is None:
                body["postings"] = []
                log.info(
                    "Validation: converted null postings to empty array in POST /ledger/voucher"
                )
            # Add explicit row numbers starting from 1 (row 0 is reserved for system-generated VAT lines)
            postings = body.get("postings", [])
            if isinstance(postings, list):
                for idx, posting in enumerate(postings):
                    if isinstance(posting, dict) and "row" not in posting:
                        posting["row"] = idx + 1
                        log.info(f"Validation: added row={idx + 1} to voucher posting")

        # NOTE: product "number" field is KEPT — the scoring system checks for it.
        # Only strip if we get a duplicate-number error at runtime (deterministic fix below).

        # Fix fixedPrice → fixedprice on POST /project (API uses lowercase 'p')
        if method == "POST" and path == "/project" and isinstance(body, dict):
            if "fixedPrice" in body:
                body["fixedprice"] = body.pop("fixedPrice")
                log.info("Validation: fixed fixedPrice → fixedprice on POST /project")
            # Ensure isFixedPrice=true when fixedprice amount is set
            if "fixedprice" in body and not body.get("isFixedPrice"):
                body["isFixedPrice"] = True
                log.info("Validation: set isFixedPrice=true on POST /project")

        # Fix field names on accounting dimension endpoints
        if method == "POST" and "/ledger/accountingDimension" in path and isinstance(body, dict):
            if "Value" in path and "name" in body and "displayName" not in body:
                body["displayName"] = body.pop("name")
                log.info("Validation: fixed name → displayName on accountingDimensionValue")
            elif "Name" in path and "name" in body and "dimensionName" not in body:
                body["dimensionName"] = body.pop("name")
                log.info("Validation: fixed name → dimensionName on accountingDimensionName")

        # Fix employmentPercentage → percentageOfFullTimeEquivalent on employment/details
        if method == "POST" and "/employment/details" in path and isinstance(body, dict):
            if "employmentPercentage" in body and "percentageOfFullTimeEquivalent" not in body:
                body["percentageOfFullTimeEquivalent"] = body.pop("employmentPercentage")
                log.info("Validation: fixed employmentPercentage → percentageOfFullTimeEquivalent")
            # Fix occupationCode: bare string → {"id": <int>}
            oc = body.get("occupationCode")
            if isinstance(oc, str):
                try:
                    body["occupationCode"] = {"id": int(oc)}
                    log.info(f"Validation: fixed occupationCode string → {{id: {oc}}}")
                except ValueError:
                    del body["occupationCode"]
                    log.info(f"Validation: removed invalid occupationCode '{oc}'")

        # Fix /project/projectActivity body: needs activity:{id}, not {name}
        if method == "POST" and "/project/projectActivity" in path and isinstance(body, dict):
            act = body.get("activity")
            if isinstance(act, dict) and "name" in act and "id" not in act:
                # Can't create with name — need to create activity separately first
                # Remove name so it doesn't cause 422, keep activity ref if it has id
                log.info("Validation: /project/projectActivity needs activity:{id}, not {name}")

        # Fix hallucinated /report/ paths → correct endpoints
        if isinstance(path, str) and path.startswith("/report/"):
            path_lower = path.lower()
            if "profitandloss" in path_lower or "result" in path_lower:
                args["path"] = "/resultbudget/company"
                args["method"] = "GET"
                log.info(f"Validation: fixed {path} → /resultbudget/company")
            elif "balance" in path_lower:
                args["path"] = "/balanceSheet"
                args["method"] = "GET"
                log.info(f"Validation: fixed {path} → /balanceSheet")
            elif "ledger" in path_lower or "posting" in path_lower:
                args["path"] = "/ledger/posting"
                args["method"] = "GET"
                log.info(f"Validation: fixed {path} → /ledger/posting")
            path = args.get("path", path)

        # Fix PUT /company/{id} → PUT /company (singleton endpoint, no ID in path)
        if method == "PUT" and re.match(r"^/company/\d+$", path):
            args["path"] = "/company"
            log.info("Validation: fixed PUT /company/{id} → PUT /company (singleton)")

        # Fix 3b: Auto-inject paymentTypeId when paidAmount present on /:invoice
        if method == "PUT" and "/:invoice" in path:
            qp = args.get("query_params", {})
            if isinstance(qp, dict):
                if "paidAmount" in qp and "paymentTypeId" not in qp:
                    qp["paymentTypeId"] = 0
                    log.info(
                        "Validation: auto-injected paymentTypeId=0 for /:invoice (required with paidAmount)"
                    )
                if "invoiceDate" not in qp:
                    qp["invoiceDate"] = date.today().isoformat()
                    log.info("Validation: auto-injected invoiceDate for /:invoice")

        if not body or not isinstance(body, dict):
            continue

        # Normalize path: /customer/123 → /customer/{id}
        template = _path_to_template(path)
        key = f"{method} {template}"
        card = ENDPOINT_CARDS.get(key)
        if not card:
            continue

        # Check 1: Add missing required fields with defaults
        for field_name, field_info in card.get("fields", {}).items():
            if field_info.get("required") and field_name not in body:
                default = field_info.get("default")
                if default:
                    body[field_name] = default
                    log.info(
                        f"Validation: added missing {field_name}={default} to {key}"
                    )
                # Special case: deliveryDate copies from orderDate
                if field_name == "deliveryDate" and "orderDate" in body:
                    body["deliveryDate"] = body["orderDate"]
                    log.info(f"Validation: set deliveryDate=orderDate for {key}")

        # Check 2: Remove conflicting fields
        for conflict_pair in card.get("conflicts", []):
            present = [f for f in conflict_pair if f in body]
            if len(present) > 1:
                for f in present[1:]:
                    del body[f]
                    log.info(f"Validation: removed conflicting field {f} from {key}")

        # Also check nested array items (e.g. orderLines)
        for field_name, field_info in card.get("fields", {}).items():
            if field_info.get("type") == "array" and field_info.get("items_fields"):
                items = body.get(field_name, [])
                if not isinstance(items, list):
                    continue
                # Build conflict pairs from items_fields
                item_conflicts = []
                for if_name, if_info in field_info["items_fields"].items():
                    if "conflicts_with" in if_info:
                        pair = sorted([if_name, if_info["conflicts_with"]])
                        if pair not in item_conflicts:
                            item_conflicts.append(pair)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    for cpair in item_conflicts:
                        cpresent = [f for f in cpair if f in item]
                        if len(cpresent) > 1:
                            for f in cpresent[1:]:
                                del item[f]
                                log.info(
                                    f"Validation: removed conflicting {f} from {field_name} item in {key}"
                                )

        # Check 3: Validate enum values (log warning only)
        for field_name, field_info in card.get("fields", {}).items():
            if "enum" in field_info and field_name in body:
                val = body[field_name]
                if (
                    isinstance(val, str)
                    and not val.startswith("$step_")
                    and val not in field_info["enum"]
                ):
                    log.warning(
                        f"Validation: {field_name}={val} not in {field_info['enum']}"
                    )

    return plan


def _merge_consecutive_posts_to_list(
    plan: list[dict], endpoint_cards: dict
) -> list[dict]:
    """Merge consecutive POST /X steps into a single POST /X/list when possible.

    Only merges when:
    - 2+ consecutive POST steps share the same path
    - POST {path}/list exists in endpoint_cards
    - None of the grouped steps reference each other via $step_N
    """
    # Known paths that support POST /X/list (from swagger.json)
    # Use hardcoded set because not all /list endpoints are in Tier 1 ENDPOINT_CARDS
    KNOWN_LIST_PATHS = {
        "/customer",
        "/supplier",
        "/department",
        "/product",
        "/employee",
        "/project",
        "/order",
        "/contact",
        "/order/orderline",
    }
    # Also add any from endpoint_cards dynamically
    mergeable_paths = set(KNOWN_LIST_PATHS)
    for key in endpoint_cards:
        if key.startswith("POST ") and key.endswith("/list"):
            base_path = key[5:-5]
            mergeable_paths.add(base_path)

    if not mergeable_paths:
        return plan

    # Find groups of consecutive same-path POSTs
    i = 0
    while i < len(plan):
        step = plan[i]
        if step.get("tool_name") != "call_api":
            i += 1
            continue
        args = step.get("args", {})
        if args.get("method") != "POST":
            i += 1
            continue
        path = args.get("path", "")
        if path not in mergeable_paths:
            i += 1
            continue

        # Found a POST to a mergeable path — scan for consecutive same-path POSTs
        group = [i]
        j = i + 1
        while j < len(plan):
            nstep = plan[j]
            if nstep.get("tool_name") != "call_api":
                break
            nargs = nstep.get("args", {})
            if nargs.get("method") != "POST" or nargs.get("path") != path:
                break
            group.append(j)
            j += 1

        if len(group) < 2:
            i += 1
            continue

        # Check independence: no $step_N cross-refs within the group
        group_step_nums = {plan[idx]["step_number"] for idx in group}
        has_cross_ref = False
        for idx in group:
            body_str = json.dumps(plan[idx].get("args", {}).get("body", {}))
            for sn in group_step_nums:
                if sn != plan[idx]["step_number"] and f"$step_{sn}" in body_str:
                    has_cross_ref = True
                    break
            if has_cross_ref:
                break

        if has_cross_ref:
            i = j
            continue

        # Merge: combine bodies into array
        merged_step_num = plan[group[0]]["step_number"]
        bodies = []
        old_step_nums = []
        for idx in group:
            old_step_nums.append(plan[idx]["step_number"])
            body = plan[idx].get("args", {}).get("body", {})
            bodies.append(body)

        merged_step = {
            "step_number": merged_step_num,
            "tool_name": "call_api",
            "args": {
                "method": "POST",
                "path": f"{path}/list",
                "body": bodies,
            },
            "description": f"Bulk create {path.split('/')[-1]}s ({len(bodies)} items)",
        }

        # Fix downstream refs: $step_N.value.id → $step_MERGED.values[idx].id
        # Build mapping: old_step_num → (merged_step_num, index_in_array)
        ref_mapping = {}
        for arr_idx, old_sn in enumerate(old_step_nums):
            ref_mapping[old_sn] = (merged_step_num, arr_idx)

        # Replace the group with the merged step
        plan[group[0] : group[-1] + 1] = [merged_step]

        # Fix downstream $step refs for merged steps
        for step in plan[group[0] + 1 :]:
            _rewrite_list_refs(step, ref_mapping)

        # Renumber: steps after the merged one need to shift down
        removed_count = len(group) - 1
        if removed_count > 0:
            # Build old→new step number mapping for renumbering
            old_to_new = {}
            for s in plan:
                sn = s["step_number"]
                if sn > merged_step_num and sn not in ref_mapping:
                    new_num = sn - removed_count
                    old_to_new[sn] = new_num

            # Apply renumbering to step numbers and all refs
            for s in plan:
                if s["step_number"] in old_to_new:
                    s["step_number"] = old_to_new[s["step_number"]]
            # Shift refs in all steps after the merged one
            for s in plan[group[0] + 1 :]:
                _renumber_step_refs(s, old_to_new)

        log.info(
            f"Validation: merged {len(group)}x POST {path} → 1x POST {path}/list (steps {old_step_nums} → step {merged_step_num})"
        )

        # Don't advance i — re-check from same position in case of further merges
        i += 1

    return plan


def _rewrite_list_refs(obj, ref_mapping: dict):
    """Rewrite $step_N.value.id → $step_M.values[idx].id for merged /list steps."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                for old_sn, (new_sn, arr_idx) in ref_mapping.items():
                    # Replace .value.id with .values[idx].id
                    old_ref = f"$step_{old_sn}.value."
                    new_ref = f"$step_{new_sn}.values[{arr_idx}]."
                    if old_ref in v:
                        v = v.replace(old_ref, new_ref)
                    # Also handle bare $step_N.value (without trailing field)
                    old_bare = f"$step_{old_sn}.value"
                    if v.endswith(old_bare):
                        v = v[: -len(old_bare)] + f"$step_{new_sn}.values[{arr_idx}]"
                obj[k] = v
            else:
                _rewrite_list_refs(v, ref_mapping)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                for old_sn, (new_sn, arr_idx) in ref_mapping.items():
                    old_ref = f"$step_{old_sn}.value."
                    new_ref = f"$step_{new_sn}.values[{arr_idx}]."
                    if old_ref in item:
                        item = item.replace(old_ref, new_ref)
                    old_bare = f"$step_{old_sn}.value"
                    if item.endswith(old_bare):
                        item = (
                            item[: -len(old_bare)] + f"$step_{new_sn}.values[{arr_idx}]"
                        )
                obj[i] = item
            else:
                _rewrite_list_refs(item, ref_mapping)


def _renumber_step_refs(obj, old_to_new: dict):
    """Renumber $step_N references according to old_to_new mapping."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                obj[k] = re.sub(
                    r"\$step_(\d+)",
                    lambda m: (
                        f"$step_{old_to_new.get(int(m.group(1)), int(m.group(1)))}"
                    ),
                    v,
                )
            else:
                _renumber_step_refs(v, old_to_new)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                obj[i] = re.sub(
                    r"\$step_(\d+)",
                    lambda m: (
                        f"$step_{old_to_new.get(int(m.group(1)), int(m.group(1)))}"
                    ),
                    item,
                )
            else:
                _renumber_step_refs(item, old_to_new)


def _path_to_template(path: str) -> str:
    """Convert /customer/123 → /customer/{id}, /order/456/:invoice → /order/{id}/:invoice"""
    return re.sub(r"/(\d+)", "/{id}", path)


def _ensure_bank_account(call_api_tool, error_count: int) -> tuple[str, dict, int]:
    """Ensure a bank account is registered for invoicing.

    Ensures ledger account 1920 exists with isBankAccount=true and bankAccountNumber set.
    Returns (result_str, parsed, error_count).
    """
    BANK_ACCOUNT_NUMBER = "12345678903"

    # Step 1: Ensure ledger account 1920 exists with bank account number
    search_result = call_api_tool.invoke(
        {
            "method": "GET",
            "path": "/ledger/account",
            "query_params": {
                "isBankAccount": True,
                "from": 0,
                "count": 1,
                "fields": "id,number,bankAccountNumber",
            },
        }
    )

    ledger_ok = False
    try:
        parsed = json.loads(search_result)
        values = parsed.get("values", [])
        if values and values[0].get("bankAccountNumber"):
            log.info(f"Ledger bank account exists: {values[0].get('number', '?')}")
            ledger_ok = True
        elif values:
            # Account exists but no bank account number — update it
            acct_id = values[0].get("id")
            if acct_id:
                log.info(f"Ledger account exists but missing bankAccountNumber, updating")
                call_api_tool.invoke({
                    "method": "PUT",
                    "path": f"/ledger/account/{acct_id}",
                    "body": {
                        "id": acct_id,
                        "number": values[0].get("number", 1920),
                        "name": values[0].get("name", "Bankkonto"),
                        "isBankAccount": True,
                        "bankAccountNumber": BANK_ACCOUNT_NUMBER,
                    },
                })
                ledger_ok = True
    except (json.JSONDecodeError, TypeError):
        pass

    if not ledger_ok:
        log.info("No bank account found, creating ledger account 1920")
        call_api_tool.invoke({
            "method": "POST",
            "path": "/ledger/account",
            "body": {
                "number": 1920,
                "name": "Bankkonto",
                "isBankAccount": True,
                "bankAccountNumber": BANK_ACCOUNT_NUMBER,
            },
        })

    # Return the ledger account result (bank account is registered on the ledger account itself)
    try:
        parsed = json.loads(search_result)
    except (json.JSONDecodeError, TypeError):
        parsed = {"raw": search_result}

    return search_result, parsed, error_count


def _ensure_division(call_api_tool, error_count: int) -> tuple[str, dict, int]:
    """Ensure a company division exists (required for employment).

    Searches for existing divisions first; creates one if none found.
    Returns (result_str, parsed, error_count) where parsed has {value: {id: N}}.
    """
    from datetime import date

    # Step 1: Check for existing division
    search_result = call_api_tool.invoke(
        {
            "method": "GET",
            "path": "/division",
            "query_params": {"from": 0, "count": 1, "fields": "id,name"},
        }
    )

    try:
        parsed = json.loads(search_result)
        values = parsed.get("values", [])
        if values:
            log.info(
                f"Division already exists: {values[0].get('name', '?')} (id={values[0].get('id')})"
            )
            return search_result, {"value": values[0]}, error_count
    except (json.JSONDecodeError, TypeError):
        pass

    # Step 2: Create division with a dummy sub-unit org number
    # (company's own org number is a legal entity and cannot be used for divisions)
    today = date.today().isoformat()
    log.info("Creating division with dummy sub-unit org number")
    create_result = call_api_tool.invoke(
        {
            "method": "POST",
            "path": "/division",
            "body": {
                "name": "Hovedvirksomhet",
                "startDate": today,
                "organizationNumber": "999999999",
                "municipality": {"id": 1},
                "municipalityDate": today,
            },
        }
    )

    try:
        parsed = json.loads(create_result)
        status = parsed.get("status", 0)
        if isinstance(status, int) and status >= 400:
            log.warning(f"Failed to create division: {create_result[:500]}")
            error_count += 1
        else:
            log.info(
                f"Division created successfully (id={parsed.get('value', {}).get('id')})"
            )
    except (json.JSONDecodeError, TypeError):
        parsed = {"raw": create_result}

    return create_result, parsed, error_count


def _shift_step_refs(obj, offset: int, min_step: int = 0):
    """Shift $step_N references by offset, but only for N >= min_step (in-place mutation)."""

    def _replace(m):
        n = int(m.group(1))
        return f"$step_{n + offset}" if n >= min_step else m.group(0)

    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                obj[k] = re.sub(r"\$step_(\d+)", _replace, v)
            else:
                _shift_step_refs(v, offset, min_step)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                obj[i] = re.sub(r"\$step_(\d+)", _replace, item)
            else:
                _shift_step_refs(item, offset, min_step)


def _fix_fields_dots(fields: str) -> str:
    """Convert dot-notation fields to parentheses: orders.orderLines.desc → orders(orderLines(desc))"""
    parts = fields.split(",")
    fixed_parts = []
    for part in parts:
        part = part.strip()
        if "." in part:
            segments = part.split(".")
            # Build from inside out: a.b.c → a(b(c))
            result = segments[-1]
            for seg in reversed(segments[:-1]):
                result = f"{seg}({result})"
            fixed_parts.append(result)
        else:
            fixed_parts.append(part)
    return ",".join(fixed_parts)


def _fix_date_range(query_params: dict, from_key: str, to_key: str):
    """Bump the To date by 1 day if From >= To (prevents 422)."""
    from_val = query_params.get(from_key)
    to_val = query_params.get(to_key)
    if from_val and to_val and isinstance(from_val, str) and isinstance(to_val, str):
        try:
            from datetime import timedelta

            from_date = date.fromisoformat(from_val)
            to_date = date.fromisoformat(to_val)
            if from_date >= to_date:
                new_to = (from_date + timedelta(days=1)).isoformat()
                query_params[to_key] = new_to
                log.info(
                    f"Validation: bumped {to_key} from {to_val} to {new_to} (must be > {from_key})"
                )
        except ValueError:
            pass


def _replace_ref_in_plan(plan: list[dict], ref_pattern: str, replacement: int):
    """Replace all occurrences of a $step_N reference string with a literal value in the plan."""
    for step in plan:
        _replace_ref_in_obj(step.get("args", {}), ref_pattern, replacement)


def _replace_ref_in_obj(obj, ref_pattern: str, replacement: int):
    """Recursively replace ref_pattern with replacement in nested dicts/lists."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str) and ref_pattern in v:
                if v == ref_pattern:
                    obj[k] = replacement
                else:
                    obj[k] = v.replace(ref_pattern, str(replacement))
            else:
                _replace_ref_in_obj(v, ref_pattern, replacement)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str) and ref_pattern in item:
                if item == ref_pattern:
                    obj[i] = replacement
                else:
                    obj[i] = item.replace(ref_pattern, str(replacement))
            else:
                _replace_ref_in_obj(item, ref_pattern, replacement)


# Status codes worth retrying with LLM fix (body/param errors)
RETRYABLE_STATUS_CODES = {400, 422}


def _find_unresolved_refs(obj, results: dict) -> list[str]:
    """Find all $step_N refs in obj that can't resolve from results."""
    import re
    unresolved = []
    text = json.dumps(obj, default=str)
    for m in re.finditer(r'\$step_(\d+)\.\S+', text):
        ref = m.group(0)
        step_key = f"step_{m.group(1)}"
        step_result = results.get(step_key)
        if step_result is None:
            unresolved.append(f"{ref} (step {m.group(1)} has no result)")
        elif isinstance(step_result, dict) and step_result.get("skipped"):
            unresolved.append(f"{ref} (step {m.group(1)} was skipped)")
        elif isinstance(step_result, dict) and "values" in step_result:
            vals = step_result["values"]
            if isinstance(vals, list) and len(vals) == 0:
                unresolved.append(f"{ref} (step {m.group(1)} returned empty list)")
    return unresolved or ["unknown"]


def _contains_unresolved(obj) -> bool:
    """Check if any value in a nested structure contains the _UNRESOLVED sentinel."""
    if obj is _UNRESOLVED or obj == _UNRESOLVED:
        return True
    if isinstance(obj, str) and _UNRESOLVED in obj:
        return True
    if isinstance(obj, dict):
        return any(_contains_unresolved(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_unresolved(item) for item in obj)
    return False


def _extract_text(content) -> str:
    """Extract plain text from LLM response content.

    Gemini can return a list of content blocks like
    [{'type': 'text', 'text': '...', 'extras': {...}}] instead of a string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        if parts:
            return "\n".join(parts)
    return str(content)


def _score_plan(plan: list[dict], prompt: str) -> float:
    """Score a plan for quality. Higher is better. Heavily penalizes extra steps."""
    score = 100.0
    if not plan:
        return 0.0

    # Per-step cost: every step beyond 1 costs 3 points
    n = len(plan)
    score -= (n - 1) * 3.0

    # Penalty: too few steps for complex tasks
    if n < 2 and len(prompt) > 100:
        score -= 20

    for step in plan:
        if step.get("tool_name") != "call_api":
            continue
        args = step.get("args", {})
        method = args.get("method", "")
        path = args.get("path", "")
        body = args.get("body", {})
        qp = args.get("query_params", {})

        # Bonus: combo endpoints
        if "/:invoice" in path and method == "PUT":
            if qp.get("paidAmount") or qp.get("paymentTypeId") is not None:
                score += 5  # combined invoice+payment
            if qp.get("sendToCustomer"):
                score += 5  # combined invoice+send

        # Bonus: bulk /list endpoints
        if path.endswith("/list") and method == "POST":
            score += 3

        # (vatType lookup penalty removed — agent should look up vatType IDs)

        # Penalty: unnecessary paymentType lookup
        if method == "GET" and "/invoice/paymentType" in path:
            score -= 5

        # Penalty: POST /invoice directly (error-prone, prefer order+invoice workflow)
        if method == "POST" and path == "/invoice":
            score -= 15

        # Bonus: employee dedup check
        if method == "GET" and path == "/employee":
            score += 10
        if method == "POST" and "/employee" in path:
            # Check if there's a GET /employee in the plan
            has_emp_get = any(
                s.get("args", {}).get("method") == "GET"
                and s.get("args", {}).get("path") == "/employee"
                for s in plan
                if s.get("tool_name") == "call_api"
            )
            if not has_emp_get:
                score -= 10


    # Penalty: consecutive same-path POSTs that could use /list
    try:
        from endpoint_catalog import ENDPOINT_CARDS

        KNOWN_LIST_PATHS = {
            "/customer",
            "/supplier",
            "/department",
            "/product",
            "/employee",
            "/project",
            "/order",
            "/contact",
            "/order/orderline",
        }
        mergeable_paths = set(KNOWN_LIST_PATHS)
        for key in ENDPOINT_CARDS:
            if key.startswith("POST ") and key.endswith("/list"):
                mergeable_paths.add(key[5:-5])

        prev_path = None
        consecutive = 0
        for step in plan:
            if step.get("tool_name") != "call_api":
                prev_path = None
                consecutive = 0
                continue
            args = step.get("args", {})
            path = args.get("path", "")
            method = args.get("method", "")
            if method == "POST" and path in mergeable_paths:
                if path == prev_path:
                    consecutive += 1
                    score -= 5  # penalty per extra step that could be merged
                else:
                    prev_path = path
                    consecutive = 1
            else:
                prev_path = None
                consecutive = 0
    except ImportError:
        pass

    return score


def build_agent():
    """Build the planner/executor StateGraph."""
    tools, tool_summaries = load_tools()
    tool_map = {t.name: t for t in tools}

    planner_model = os.environ.get("GEMINI_PLANNER_MODEL", "gemini-3.1-pro-preview")
    heal_model = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
    api_key = os.environ["GOOGLE_API_KEY"]

    planner_llm = ChatGoogleGenerativeAI(
        model=planner_model,
        google_api_key=api_key,
        temperature=0,
    )

    heal_llm = ChatGoogleGenerativeAI(
        model=heal_model,
        google_api_key=api_key,
        temperature=0,
    )

    llm = heal_llm

    # --- Node: planner (single model) ---
    def planner(state: AgentState) -> dict:
        prompt_text = PLANNER_PROMPT.format(
            today=date.today().isoformat(),
            tool_summaries=tool_summaries,
            task=state["original_prompt"],
        )

        full_prompt = PLANNER_PROFILE["prefix"] + "\n\n" + prompt_text
        file_parts = state.get("file_content_parts", [])
        log.info("Planner invoked", model=planner_model, prompt_length=len(full_prompt), file_parts=len(file_parts))

        # Build multimodal message if files are attached
        if file_parts:
            planner_content = [{"type": "text", "text": full_prompt}] + file_parts
        else:
            planner_content = full_prompt

        try:
            response = planner_llm.invoke([HumanMessage(content=planner_content)])
            raw = _extract_text(response.content)
            best = _parse_plan_json(raw)
            log.info(f"Planner returned {len(best)} steps")
        except Exception as e:
            log.warning(f"Planner failed: {e}")
            best = []

        # Retry with fallback model if planner returned empty plan
        if not best:
            log.warning("Empty plan from primary model — retrying with fallback model")
            try:
                response = heal_llm.invoke([HumanMessage(content=planner_content)])
                raw = _extract_text(response.content)
                best = _parse_plan_json(raw)
                log.info(f"Fallback planner returned {len(best)} steps")
            except Exception as e:
                log.warning(f"Fallback planner also failed: {e}")
                best = []

        best = validate_plan(best)

        log.info(
            f">>>PLAN_START<<<\n{json.dumps(best, indent=2)}\n>>>PLAN_END<<<",
            steps=len(best),
            steps_count=len(best),
        )

        return {
            "plan": best,
            "current_step": 0,
            "results": {},
            "completed_steps": [],
            "error_count": state.get("error_count", 0),
            "healed_steps": [],
            "messages": [AIMessage(content=f"Plan ({len(best)} steps): {json.dumps(best)}")],
        }

    def _validate_step_against_schema(resolved_args: dict) -> dict:
        """Validate and auto-fix resolved args against endpoint schema before API call.

        Returns the (possibly fixed) args dict.
        """
        method = resolved_args.get("method", "")
        path = resolved_args.get("path", "")
        body = resolved_args.get("body")

        if not body or not isinstance(body, dict):
            return resolved_args

        try:
            from generic_tools import get_endpoint_card

            card = get_endpoint_card(method, path)
        except Exception:
            return resolved_args

        if not card:
            return resolved_args

        # Strip do_not_send fields from body (but NEVER strip product number — scoring checks it)
        endpoint_path = resolved_args.get("path", "")
        for dns in card.get("do_not_send", []):
            field_name = dns.get("field", "")
            # Never strip "number" from product endpoints — scoring system checks product numbers
            if field_name == "number" and "/product" in endpoint_path:
                continue
            # Handle simple field names (not compound descriptions like "request body")
            if field_name and " " not in field_name and field_name in body:
                del body[field_name]
                log.info(
                    f"Schema pre-validation: stripped do_not_send field '{field_name}' — {dns.get('reason', '')}"
                )

        if not card.get("fields"):
            return resolved_args

        fields = card["fields"]

        # Check required fields
        for fname, finfo in fields.items():
            if finfo.get("required") and fname not in body:
                default = finfo.get("default")
                if default:
                    body[fname] = default
                    log.info(
                        f"Schema pre-validation: added missing required {fname}={default}"
                    )
                elif fname == "deliveryDate" and "orderDate" in body:
                    body["deliveryDate"] = body["orderDate"]
                    log.info("Schema pre-validation: set deliveryDate=orderDate")

        # Remove conflicting fields
        for conflict_pair in card.get("conflicts", []):
            present = [f for f in conflict_pair if f in body]
            if len(present) > 1:
                # Keep the first, remove the rest
                for f in present[1:]:
                    del body[f]
                    log.info(f"Schema pre-validation: removed conflicting field {f}")

        # Check nested array items (e.g., orderLines)
        for fname, finfo in fields.items():
            if finfo.get("type") == "array" and finfo.get("items_fields"):
                items = body.get(fname, [])
                if not isinstance(items, list):
                    continue
                item_conflicts = []
                for if_name, if_info in finfo["items_fields"].items():
                    if "conflicts_with" in if_info:
                        pair = sorted([if_name, if_info["conflicts_with"]])
                        if pair not in item_conflicts:
                            item_conflicts.append(pair)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    for cpair in item_conflicts:
                        cpresent = [f for f in cpair if f in item]
                        if len(cpresent) > 1:
                            for f in cpresent[1:]:
                                del item[f]
                                log.info(
                                    f"Schema pre-validation: removed conflicting {f} from {fname} item"
                                )

        # Validate reference format: {id: value} should have integer id
        for fname, finfo in fields.items():
            if fname in body and finfo.get("type") == "object":
                ref = body[fname]
                if isinstance(ref, dict) and "id" in ref:
                    ref_id = ref["id"]
                    if isinstance(ref_id, str) and not ref_id.startswith("$step_"):
                        # Try to coerce string numbers to int
                        try:
                            ref["id"] = int(ref_id)
                            log.info(
                                f"Schema pre-validation: coerced {fname}.id to int"
                            )
                        except ValueError:
                            log.warning(
                                f"Schema pre-validation: {fname}.id='{ref_id}' is not a valid integer"
                            )

        return resolved_args

    # --- Node: executor ---
    def executor(state: AgentState) -> dict:
        plan = state["plan"]
        step_idx = state["current_step"]
        results = dict(state.get("results", {}))
        error_count = state.get("error_count", 0)
        healed_steps = list(state.get("healed_steps", []))
        completed = list(state.get("completed_steps", []))

        if step_idx >= len(plan):
            return {"current_step": step_idx}

        step = plan[step_idx]
        tool_name = step["tool_name"]
        args = step.get("args", {})
        description = step.get("description", f"Step {step['step_number']}")

        log.info(
            f"Executing step {step['step_number']}: {description}",
            tool=tool_name,
            tool_args=args,
        )

        # Handle ensure_bank_account meta-step
        if tool_name == "ensure_bank_account":
            call_api_tool = tool_map.get("call_api")
            if call_api_tool:
                result_str, parsed, error_count = _ensure_bank_account(
                    call_api_tool, error_count
                )
                results[f"step_{step['step_number']}"] = parsed
                log.info(f"Step {step['step_number']} completed: bank account ensured")
                completed.append(step["step_number"])
                return {
                    "current_step": step_idx + 1,
                    "results": results,
                    "completed_steps": completed,
                    "error_count": error_count,
                    "healed_steps": healed_steps,
                    "messages": [
                        AIMessage(
                            content=f"Step {step['step_number']} done: bank account ensured"
                        )
                    ],
                }

        # Handle ensure_division meta-step
        if tool_name == "ensure_division":
            call_api_tool = tool_map.get("call_api")
            if call_api_tool:
                result_str, parsed, error_count = _ensure_division(
                    call_api_tool, error_count
                )
                results[f"step_{step['step_number']}"] = parsed
                log.info(f"Step {step['step_number']} completed: division ensured")
                completed.append(step["step_number"])
                return {
                    "current_step": step_idx + 1,
                    "results": results,
                    "completed_steps": completed,
                    "error_count": error_count,
                    "healed_steps": healed_steps,
                    "messages": [
                        AIMessage(
                            content=f"Step {step['step_number']} done: division ensured"
                        )
                    ],
                }

        # Resolve $step_N placeholders recursively through nested dicts/lists
        resolved_args = _resolve_placeholders_deep(args, results, llm)

        # Fail steps with unresolved dependencies — log exactly which ref failed
        if _contains_unresolved(resolved_args):
            # Find which $step_N refs are unresolved
            unresolved_refs = _find_unresolved_refs(args, results)
            log.warning(
                f"Step {step['step_number']} FAILED: unresolved refs: {unresolved_refs}. "
                f"Original args: {json.dumps(args, default=str)[:300]}"
            )
            results[f"step_{step['step_number']}"] = {
                "skipped": True,
                "reason": f"unresolved: {unresolved_refs}",
            }
            error_count += 1
            completed.append(step["step_number"])
            return {
                "current_step": step_idx + 1,
                "results": results,
                "error_count": error_count,
                "healed_steps": healed_steps,
                "completed_steps": completed,
                "messages": [
                    AIMessage(
                        content=f"Step {step['step_number']} failed: unresolved {unresolved_refs}"
                    )
                ],
            }

        # Employee dedup: skip POST /employee if GET already found the employee
        if (
            tool_name == "call_api"
            and resolved_args.get("method") == "POST"
            and resolved_args.get("path") == "/employee"
        ):
            emp_email = None
            emp_body = resolved_args.get("body", {})
            if isinstance(emp_body, dict):
                emp_email = emp_body.get("email", "").lower()
            if emp_email:
                # Search previous results for a GET /employee that found this email
                for prev_key, prev_result in results.items():
                    if not isinstance(prev_result, dict):
                        continue
                    prev_values = prev_result.get("values", [])
                    if isinstance(prev_values, list) and prev_values:
                        for v in prev_values:
                            if (
                                isinstance(v, dict)
                                and v.get("email", "").lower() == emp_email
                            ):
                                log.info(
                                    f"Employee already exists (from {prev_key}, id={v.get('id')}), skipping POST /employee"
                                )
                                # Store the GET result as this step's result so downstream $step refs work
                                results[f"step_{step['step_number']}"] = {"value": v}
                                completed.append(step["step_number"])
                                return {
                                    "current_step": step_idx + 1,
                                    "results": results,
                                    "completed_steps": completed,
                                    "error_count": error_count,
                                    "healed_steps": healed_steps,
                                    "messages": [
                                        AIMessage(
                                            content=f"Step {step['step_number']} skipped: employee {emp_email} already exists (id={v.get('id')})"
                                        )
                                    ],
                                }

        # Call the tool
        if tool_name not in tool_map:
            error_msg = f"Unknown tool: {tool_name}"
            log.error(error_msg)
            results[f"step_{step['step_number']}"] = {"error": error_msg}
            error_count += 1
            completed.append(step["step_number"])
            return {
                "current_step": step_idx + 1,
                "results": results,
                "error_count": error_count,
                "healed_steps": healed_steps,
                "completed_steps": completed,
                "messages": [AIMessage(content=f"Error: {error_msg}")],
            }

        tool = tool_map[tool_name]

        # Schema pre-validation (auto-fix before hitting the API)
        if tool_name == "call_api":
            resolved_args = _validate_step_against_schema(resolved_args)

        # First attempt
        try:
            result_str = tool.invoke(resolved_args)
        except Exception as e:
            error_msg = f"Tool {tool.name} raised: {str(e)}"
            log.error(error_msg)
            results[f"step_{step['step_number']}"] = {"error": error_msg}
            error_count += 1
            completed.append(step["step_number"])
            return {
                "current_step": step_idx + 1,
                "results": results,
                "error_count": error_count,
                "healed_steps": healed_steps,
                "completed_steps": completed,
                "messages": [AIMessage(content=f"Error: {error_msg}")],
            }

        is_error, status_code = _is_api_error(result_str)

        if not is_error:
            # Success on first try
            try:
                parsed = json.loads(result_str)
            except (json.JSONDecodeError, TypeError):
                parsed = {"raw": result_str}
            results[f"step_{step['step_number']}"] = parsed
            log.info(
                f"Step {step['step_number']} completed",
                result_preview=str(parsed)[:500],
            )
            completed.append(step["step_number"])
            return {
                "current_step": step_idx + 1,
                "results": results,
                "completed_steps": completed,
                "error_count": error_count,
                "healed_steps": healed_steps,
                "messages": [
                    AIMessage(
                        content=f"Step {step['step_number']} done: {str(parsed)[:200]}"
                    )
                ],
            }

        # API error — try deterministic fixes first, then LLM replan
        error_lower = result_str.lower() if result_str else ""

        # Fatal: 403 expired/invalid proxy token — abort all remaining steps
        if status_code == 403 and ("proxy token" in error_lower or "expired" in error_lower):
            log.warning(
                "FATAL: 403 expired proxy token — aborting all remaining steps to save API budget"
            )
            error_count += 1
            # Mark all remaining steps as done to stop the executor
            return {
                "current_step": len(plan),  # skip to end
                "results": results,
                "completed_steps": completed,
                "error_count": error_count,
                "healed_steps": healed_steps,
                "messages": [
                    AIMessage(
                        content="ABORTED: proxy token expired/invalid, no further API calls possible"
                    )
                ],
            }

        # Deterministic fix: bank account not registered
        if status_code in RETRYABLE_STATUS_CODES and "bankkontonummer" in error_lower:
            log.info(
                "Deterministic fix: bank account missing, running ensure_bank_account and retrying"
            )
            call_api_tool = tool_map.get("call_api")
            if call_api_tool:
                _, _, error_count = _ensure_bank_account(call_api_tool, error_count)
                try:
                    retry_result_str = tool.invoke(resolved_args)
                    retry_is_error, retry_status = _is_api_error(retry_result_str)
                    if not retry_is_error:
                        try:
                            parsed = json.loads(retry_result_str)
                        except (json.JSONDecodeError, TypeError):
                            parsed = {"raw": retry_result_str}
                        results[f"step_{step['step_number']}"] = parsed
                        log.info(
                            f"Step {step['step_number']} succeeded after bank account fix"
                        )
                        completed.append(step["step_number"])
                        return {
                            "current_step": step_idx + 1,
                            "results": results,
                            "completed_steps": completed,
                            "error_count": error_count,
                            "healed_steps": healed_steps,
                            "messages": [
                                AIMessage(
                                    content=f"Step {step['step_number']} done (bank account fixed): {str(parsed)[:200]}"
                                )
                            ],
                        }
                except Exception:
                    pass  # fall through to LLM replan

        # Deterministic fix: missing department.id on employee
        if (
            status_code in RETRYABLE_STATUS_CODES
            and "department" in error_lower
            and "/employee" in resolved_args.get("path", "")
        ):
            log.info("Deterministic fix: missing department.id, fetching department")
            call_api_tool = tool_map.get("call_api")
            if call_api_tool:
                dept_result = call_api_tool.invoke(
                    {
                        "method": "GET",
                        "path": "/department",
                        "query_params": {"from": 0, "count": 1, "fields": "id"},
                    }
                )
                try:
                    dept_parsed = json.loads(dept_result)
                    dept_values = dept_parsed.get("values", [])
                    if dept_values:
                        dept_id = dept_values[0].get("id")
                        if dept_id and isinstance(resolved_args.get("body"), dict):
                            resolved_args["body"]["department"] = {"id": dept_id}
                            retry_result_str = tool.invoke(resolved_args)
                            retry_is_error, _ = _is_api_error(retry_result_str)
                            if not retry_is_error:
                                try:
                                    parsed = json.loads(retry_result_str)
                                except (json.JSONDecodeError, TypeError):
                                    parsed = {"raw": retry_result_str}
                                results[f"step_{step['step_number']}"] = parsed
                                log.info(
                                    f"Step {step['step_number']} succeeded after department fix"
                                )
                                completed.append(step["step_number"])
                                return {
                                    "current_step": step_idx + 1,
                                    "results": results,
                                    "completed_steps": completed,
                                    "error_count": error_count,
                                    "healed_steps": healed_steps,
                                    "messages": [
                                        AIMessage(
                                            content=f"Step {step['step_number']} done (department fixed)"
                                        )
                                    ],
                                }
                except (json.JSONDecodeError, TypeError, Exception):
                    pass  # fall through to LLM replan

        # Deterministic fix: duplicate product number
        if (
            status_code in RETRYABLE_STATUS_CODES
            and "produktnummeret" in error_lower
            and "er i bruk" in error_lower
        ):
            log.info(
                "Deterministic fix: duplicate product number, stripping number field"
            )
            body = resolved_args.get("body")
            if isinstance(body, list):
                for item in body:
                    if isinstance(item, dict):
                        item.pop("number", None)
            elif isinstance(body, dict):
                body.pop("number", None)
            try:
                retry_result_str = tool.invoke(resolved_args)
                retry_is_error, _ = _is_api_error(retry_result_str)
                if not retry_is_error:
                    try:
                        parsed = json.loads(retry_result_str)
                    except (json.JSONDecodeError, TypeError):
                        parsed = {"raw": retry_result_str}
                    results[f"step_{step['step_number']}"] = parsed
                    log.info(
                        f"Step {step['step_number']} succeeded after product number fix"
                    )
                    completed.append(step["step_number"])
                    return {
                        "current_step": step_idx + 1,
                        "results": results,
                        "completed_steps": completed,
                        "error_count": error_count,
                        "healed_steps": healed_steps,
                        "messages": [
                            AIMessage(
                                content=f"Step {step['step_number']} done (product number fixed)"
                            )
                        ],
                    }
            except Exception:
                pass  # fall through to LLM replan

        # (Duplicate email handler removed — executor-level employee dedup skip prevents this)

        # Deterministic fix: price field conflict (priceIncludingVatCurrency vs priceExcludingVatCurrency)
        if status_code in RETRYABLE_STATUS_CODES and (
            "priceincludingvat" in error_lower or "price" in error_lower
        ):
            body = resolved_args.get("body")
            fixed = False
            items_to_check = []
            if isinstance(body, list):
                items_to_check = [item for item in body if isinstance(item, dict)]
            elif isinstance(body, dict):
                items_to_check = [body]
                # Also check nested arrays like orderLines
                for v in body.values():
                    if isinstance(v, list):
                        items_to_check.extend(
                            item for item in v if isinstance(item, dict)
                        )
            for item in items_to_check:
                if (
                    "priceIncludingVatCurrency" in item
                    and "priceExcludingVatCurrency" in item
                ):
                    del item["priceIncludingVatCurrency"]
                    fixed = True
                    log.info(
                        "Deterministic fix: removed priceIncludingVatCurrency (conflicts with priceExcludingVatCurrency)"
                    )
            if fixed:
                try:
                    retry_result_str = tool.invoke(resolved_args)
                    retry_is_error, _ = _is_api_error(retry_result_str)
                    if not retry_is_error:
                        try:
                            parsed = json.loads(retry_result_str)
                        except (json.JSONDecodeError, TypeError):
                            parsed = {"raw": retry_result_str}
                        results[f"step_{step['step_number']}"] = parsed
                        log.info(
                            f"Step {step['step_number']} succeeded after price field conflict fix"
                        )
                        completed.append(step["step_number"])
                        return {
                            "current_step": step_idx + 1,
                            "results": results,
                            "completed_steps": completed,
                            "error_count": error_count,
                            "healed_steps": healed_steps,
                            "messages": [
                                AIMessage(
                                    content=f"Step {step['step_number']} done (price conflict fixed)"
                                )
                            ],
                        }
                except Exception:
                    pass

        # Deterministic fix: voucher posting row numbering error
        if (
            status_code in RETRYABLE_STATUS_CODES
            and (
                "rad 0" in error_lower
                or "guirow" in error_lower
                or "row" in error_lower
            )
            and "/ledger/voucher" in resolved_args.get("path", "")
        ):
            body = resolved_args.get("body")
            if isinstance(body, dict) and "postings" in body:
                postings = body["postings"]
                if isinstance(postings, list):
                    for idx_p, posting in enumerate(postings):
                        if isinstance(posting, dict):
                            posting["row"] = idx_p + 1
                    log.info(
                        f"Deterministic fix: re-numbered {len(postings)} voucher postings from row 1"
                    )
                    try:
                        retry_result_str = tool.invoke(resolved_args)
                        retry_is_error, _ = _is_api_error(retry_result_str)
                        if not retry_is_error:
                            try:
                                parsed = json.loads(retry_result_str)
                            except (json.JSONDecodeError, TypeError):
                                parsed = {"raw": retry_result_str}
                            results[f"step_{step['step_number']}"] = parsed
                            log.info(
                                f"Step {step['step_number']} succeeded after row numbering fix"
                            )
                            completed.append(step["step_number"])
                            return {
                                "current_step": step_idx + 1,
                                "results": results,
                                "completed_steps": completed,
                                "error_count": error_count,
                                "healed_steps": healed_steps,
                                "messages": [
                                    AIMessage(
                                        content=f"Step {step['step_number']} done (row numbering fixed)"
                                    )
                                ],
                            }
                    except Exception:
                        pass

        # Deterministic fix: displayName/dimensionName on accounting dimension endpoints
        if (
            status_code in RETRYABLE_STATUS_CODES
            and "kan ikke" in error_lower
            and "/ledger/accountingdimension" in resolved_args.get("path", "").lower()
        ):
            body = resolved_args.get("body")
            fixed = False
            if isinstance(body, dict) and "name" in body:
                path_str = resolved_args.get("path", "")
                if "Value" in path_str and "displayName" not in body:
                    body["displayName"] = body.pop("name")
                    fixed = True
                    log.info("Deterministic fix: name → displayName on accountingDimensionValue")
                elif "Name" in path_str and "dimensionName" not in body:
                    body["dimensionName"] = body.pop("name")
                    fixed = True
                    log.info("Deterministic fix: name → dimensionName on accountingDimensionName")
            if fixed:
                try:
                    retry_result_str = tool.invoke(resolved_args)
                    retry_is_error, _ = _is_api_error(retry_result_str)
                    if not retry_is_error:
                        try:
                            parsed = json.loads(retry_result_str)
                        except (json.JSONDecodeError, TypeError):
                            parsed = {"raw": retry_result_str}
                        results[f"step_{step['step_number']}"] = parsed
                        completed.append(step["step_number"])
                        return {
                            "current_step": step_idx + 1,
                            "results": results,
                            "completed_steps": completed,
                            "error_count": error_count,
                            "healed_steps": healed_steps,
                            "messages": [AIMessage(content=f"Step {step['step_number']} done (dimension field fix)")],
                        }
                except Exception:
                    pass

        # Deterministic fix: projectManager lacks entitlements
        if (
            status_code in RETRYABLE_STATUS_CODES
            and ("prosjektleder" in error_lower or "project manager" in error_lower or "rettigheter" in error_lower)
            and "/project" in resolved_args.get("path", "")
        ):
            call_api_tool = tool_map.get("call_api")
            pm = resolved_args.get("body", {})
            if isinstance(pm, dict):
                pm = pm.get("projectManager", {})
            pm_id = pm.get("id") if isinstance(pm, dict) else None
            if call_api_tool and pm_id and not isinstance(pm_id, str):
                log.info(f"Deterministic fix: granting entitlements to projectManager {pm_id}")
                call_api_tool.invoke({
                    "method": "PUT",
                    "path": "/employee/entitlement/:grantEntitlementsByTemplate",
                    "query_params": {"employeeId": int(pm_id), "template": "ALL_PRIVILEGES"},
                })
                try:
                    retry_result_str = tool.invoke(resolved_args)
                    retry_is_error, _ = _is_api_error(retry_result_str)
                    if not retry_is_error:
                        try:
                            parsed = json.loads(retry_result_str)
                        except (json.JSONDecodeError, TypeError):
                            parsed = {"raw": retry_result_str}
                        results[f"step_{step['step_number']}"] = parsed
                        completed.append(step["step_number"])
                        return {
                            "current_step": step_idx + 1,
                            "results": results,
                            "completed_steps": completed,
                            "error_count": error_count,
                            "healed_steps": healed_steps,
                            "messages": [AIMessage(content=f"Step {step['step_number']} done (entitlements fixed)")],
                        }
                except Exception:
                    pass

        # ── Self-heal: FIX_ARGS only (1 attempt, no REPLAN) ──
        if status_code in RETRYABLE_STATUS_CODES and step["step_number"] not in healed_steps:
            log.warning(f"API error {status_code}, attempting FIX_ARGS")
            fixed_args = _ask_llm_to_fix_args(heal_llm, resolved_args, result_str)
            if fixed_args:
                _log_self_heal(tool.name, resolved_args, result_str, fixed_args, retry_succeeded=True)
                try:
                    retry_result_str = tool.invoke(fixed_args)
                except Exception as e:
                    retry_result_str = json.dumps({"error": str(e)})

                retry_is_error, retry_status = _is_api_error(retry_result_str)
                if not retry_is_error:
                    try:
                        parsed = json.loads(retry_result_str)
                    except (json.JSONDecodeError, TypeError):
                        parsed = {"raw": retry_result_str}
                    results[f"step_{step['step_number']}"] = parsed
                    log.info(f"Step {step['step_number']} succeeded after FIX_ARGS")
                    completed.append(step["step_number"])
                    return {
                        "current_step": step_idx + 1,
                        "results": results,
                        "completed_steps": completed,
                        "error_count": error_count,
                        "healed_steps": healed_steps + [step["step_number"]],
                        "messages": [AIMessage(content=f"Step {step['step_number']} done (FIX_ARGS): {str(parsed)[:200]}")],
                    }
                else:
                    log.warning(f"FIX_ARGS retry also failed with status {retry_status}")
                    _log_self_heal(tool.name, resolved_args, result_str, fixed_args, retry_succeeded=False)

        # Out of replans or non-retryable — record error and move on
        log.warning(f"Step {step['step_number']} failed with status {status_code}")
        try:
            parsed = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            parsed = {"raw": result_str}
        results[f"step_{step['step_number']}"] = parsed
        error_count += 1
        completed.append(step["step_number"])
        return {
            "current_step": step_idx + 1,
            "results": results,
            "completed_steps": completed,
            "error_count": error_count,
            "healed_steps": healed_steps,
            "messages": [
                AIMessage(
                    content=f"Step {step['step_number']} failed: {str(parsed)[:200]}"
                )
            ],
        }

    # --- Node: check_done ---
    def check_done(state: AgentState) -> str:
        if state["current_step"] >= len(state["plan"]):
            log.info("All steps completed, routing to verifier")
            return "verify"
        if state.get("error_count", 0) >= 3:
            log.warning("Too many errors, aborting to preserve efficiency score")
            return "verify"
        return "continue"

    # --- Node: verifier (post-execution check) ---
    def verifier(state: AgentState) -> dict:
        verification_attempts = state.get("verification_attempts", 0)

        # Skip verification if all steps succeeded (no wasted LLM call)
        results = state.get("results", {})
        plan = state.get("plan", [])
        has_failures = any(
            isinstance(r, dict)
            and (
                r.get("skipped")
                or r.get("error")
                or (isinstance(r.get("status"), int) and r["status"] >= 400)
            )
            for r in results.values()
        )

        if not has_failures:
            log.info("All steps succeeded — skipping verification")
            return {"verification_attempts": verification_attempts}

        # Max 1 verification round
        if verification_attempts >= 1:
            log.info("Verification already attempted, finishing")
            return {"verification_attempts": verification_attempts}

        # Build summaries for the LLM
        plan_summary = "\n".join(
            f"  Step {s['step_number']}: {s.get('description', '?')} — {s.get('args', {}).get('method', '')} {s.get('args', {}).get('path', '')}"
            for s in plan
        )

        results_summary = "\n".join(
            f"  {k}: {json.dumps(v, default=str)[:300]}"
            for k, v in sorted(results.items())
        )

        failed_steps_list = []
        for s in plan:
            key = f"step_{s['step_number']}"
            r = results.get(key, {})
            if isinstance(r, dict) and (
                r.get("skipped")
                or r.get("error")
                or (isinstance(r.get("status"), int) and r["status"] >= 400)
            ):
                failed_steps_list.append(
                    f"  Step {s['step_number']}: {s.get('description', '?')} — {json.dumps(r, default=str)[:200]}"
                )
        failed_str = "\n".join(failed_steps_list) if failed_steps_list else "  (none)"

        next_step = max((s["step_number"] for s in plan), default=0) + 1

        prompt = VERIFY_PROMPT.format(
            task=state["original_prompt"][:1000],
            plan_summary=plan_summary,
            results_summary=results_summary[:3000],
            failed_steps=failed_str,
            next_step_number=next_step,
        )

        try:
            resp = planner_llm.invoke([HumanMessage(content=prompt)])
            raw = _extract_text(resp.content)
            parsed = _parse_json_object(raw)

            if parsed and isinstance(parsed, dict):
                if parsed.get("verified"):
                    log.info("Verifier: task verified as complete")
                    return {"verification_attempts": verification_attempts + 1}
                else:
                    corrective_steps = parsed.get("corrective_steps", [])
                    if corrective_steps:
                        # Fix malformed corrective steps (e.g., "endpoint" instead of "method"+"path")
                        for cs in corrective_steps:
                            args = cs.get("args", {})
                            if "endpoint" in args and "method" not in args:
                                ep = args.pop("endpoint", "")
                                parts = ep.strip().split(" ", 1)
                                if len(parts) == 2:
                                    args["method"] = parts[0]
                                    args["path"] = parts[1]
                                elif ep.startswith("/"):
                                    args["method"] = "GET"
                                    args["path"] = ep
                                log.info(
                                    f"Verifier: fixed malformed step format (endpoint → method+path)"
                                )
                        corrective_steps = validate_plan(corrective_steps)
                        log.info(
                            f"Verifier: task incomplete, adding {len(corrective_steps)} corrective steps"
                        )
                        new_plan = plan + corrective_steps
                        return {
                            "plan": new_plan,
                            "current_step": len(
                                plan
                            ),  # start executing from the new steps
                            "verification_attempts": verification_attempts + 1,
                            "messages": [
                                AIMessage(
                                    content=f"Verifier adding {len(corrective_steps)} corrective steps"
                                )
                            ],
                        }
                    else:
                        log.info(
                            "Verifier: task incomplete but no corrective steps suggested"
                        )
                        return {"verification_attempts": verification_attempts + 1}
        except Exception as e:
            log.warning(f"Verifier LLM call failed: {e}")

        return {"verification_attempts": verification_attempts + 1}

    # --- Routing from verifier ---
    def after_verify(state: AgentState) -> str:
        # If verifier added corrective steps and we haven't finished them
        if state["current_step"] < len(state["plan"]):
            return "continue"
        return "end"

    # Build graph
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner)
    graph.add_node("executor", executor)
    graph.add_node("verifier", verifier)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "executor")
    graph.add_conditional_edges(
        "executor",
        check_done,
        {"continue": "executor", "verify": "verifier"},
    )
    graph.add_conditional_edges(
        "verifier",
        after_verify,
        {"continue": "executor", "end": END},
    )

    return graph.compile()


def run_agent(agent, prompt: str, file_attachments: list = None) -> None:
    """Run the agent with the given prompt and optional file attachments.

    file_attachments: list of dicts, each with:
      - type: "text" or "binary"
      - filename: str
      - text: str (for text files)
      - content_base64: str (for binary files — PDFs, images)
      - mime_type: str (for binary files)
    """
    # Build multimodal file content parts (for planner LLM calls)
    file_content_parts = []
    if file_attachments:
        for f in file_attachments:
            if f["type"] == "text":
                file_content_parts.append({"type": "text", "text": f"\n[File: {f['filename']}]\n{f['text']}"})
            else:
                # Binary file (PDF, image) — pass as inline data for Gemini
                data_url = f"data:{f['mime_type']};base64,{f['content_base64']}"
                file_content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
                file_content_parts.append({"type": "text", "text": f"[The above is file: {f['filename']}]"})

    message = HumanMessage(content=prompt)
    original_prompt = prompt

    log.info("Invoking agent", prompt_length=len(prompt), files=len(file_attachments or []))

    initial_state = {
        "messages": [message],
        "plan": [],
        "current_step": 0,
        "results": {},
        "completed_steps": [],
        "error_count": 0,
        "healed_steps": [],
        "original_prompt": original_prompt,
        "file_content_parts": file_content_parts,
        "verification_attempts": 0,
    }

    result = agent.invoke(initial_state)

    # Log final state
    completed = result.get("completed_steps", [])
    errors = result.get("error_count", 0)
    healed = result.get("healed_steps", [])
    log.info(
        "Agent finished",
        completed_steps=len(completed),
        total_steps=len(result.get("plan", [])),
        errors=errors,
        healed_steps=len(healed),
    )


def _parse_plan_json(raw: str) -> list[dict]:
    """Extract JSON array from LLM response, handling markdown code blocks."""
    # Try to find JSON in code blocks first
    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if code_match:
        raw = code_match.group(1)

    # Try to find a JSON array
    bracket_match = re.search(r"\[.*\]", raw, re.DOTALL)
    if bracket_match:
        try:
            return json.loads(bracket_match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback: try the whole string
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.error("Failed to parse plan JSON", raw=raw[:500])
        return []


def _is_api_error(result_str: str) -> tuple[bool, int]:
    """Check if the API response indicates a 4xx/5xx error.

    Returns (is_error, status_code).
    """
    try:
        parsed = json.loads(result_str)
        status = parsed.get("status", 0)
        if isinstance(status, int) and status >= 400:
            return True, status
        return False, 0
    except (json.JSONDecodeError, TypeError):
        # Detect HTML error pages (e.g. 405 Method Not Allowed)
        status_match = re.search(r"HTTP Status (\d{3})", result_str)
        if status_match:
            code = int(status_match.group(1))
            if code >= 400:
                return True, code
        # Any HTML response from the API is an error
        if "<html" in result_str.lower():
            return True, 500
        return False, 0


def _log_self_heal(
    tool_name: str,
    original_args: dict,
    error_response: str,
    fixed_args: dict | None,
    retry_succeeded: bool,
) -> None:
    """Log a self-heal attempt with clear delimiters for easy extraction from cloud logs."""
    log.warning(
        ">>>SELF_HEAL_START<<<\n"
        f"tool: {tool_name}\n"
        f"original_args: {json.dumps(original_args, indent=2, default=str)}\n"
        f"api_error: {error_response[:2000]}\n"
        f"llm_fix: {json.dumps(fixed_args, indent=2, default=str) if fixed_args else 'NONE'}\n"
        f"retry_succeeded: {retry_succeeded}\n"
        ">>>SELF_HEAL_END<<<",
        tool=tool_name,
        retry_succeeded=retry_succeeded,
    )


def _ask_llm_to_replan(
    llm,
    original_args: dict,
    error_response: str,
    remaining_steps: list[dict],
    results: dict,
    original_task: str,
    next_step_number: int,
) -> dict | None:
    """Ask the LLM to decide how to proceed after an API error.

    Returns one of:
    - {"action": "retry", "args": {...}}
    - {"action": "skip", "reason": "..."}
    - {"action": "replace", "steps": [...]}
    - None on failure
    """
    method = original_args.get("method", "POST")
    path = original_args.get("path", "")

    # Get endpoint schema for rich context
    try:
        from generic_tools import get_endpoint_schema, get_common_errors

        endpoint_schema = get_endpoint_schema(method, path)
        common_errors = get_common_errors(method, path)
    except Exception:
        endpoint_schema = "(unavailable)"
        common_errors = "(none)"

    # Format remaining steps and previous results compactly
    remaining_str = (
        json.dumps(remaining_steps, indent=2, default=str)[:2000]
        if remaining_steps
        else "[]"
    )
    results_str = json.dumps(
        {k: str(v)[:200] for k, v in results.items()},
        indent=2,
        default=str,
    )[:2000]

    prompt = REPLAN_PROMPT.format(
        method=method,
        path=path,
        args=json.dumps(original_args, indent=2, default=str)[:1500],
        error_response=error_response[:2000],
        endpoint_schema=str(endpoint_schema)[:3000],
        common_errors=common_errors,
        remaining_steps=remaining_str,
        previous_results=results_str,
        original_task=original_task[:500],
        next_step_number=next_step_number,
    )

    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = _extract_text(resp.content)
        parsed = _parse_json_object(raw)
        if parsed and isinstance(parsed, dict) and "action" in parsed:
            # Sanitize /v2 prefix from paths in replan response
            _strip_v2_from_replan(parsed)
            log.info(f"Replan decision: {parsed.get('action')}", replan=parsed)
            return parsed
    except Exception as e:
        log.warning(f"Replan LLM call failed: {e}")

    return None


def _ask_llm_to_fix_args(
    llm,
    original_args: dict,
    error_response: str,
) -> dict | None:
    """Quick LLM fix: just fix the args, no replan/skip/replace decisions.

    Returns fixed args dict or None on failure.
    """
    method = original_args.get("method", "POST")
    path = original_args.get("path", "")

    try:
        from generic_tools import get_endpoint_schema, get_common_errors

        endpoint_schema = get_endpoint_schema(method, path)
        common_errors = get_common_errors(method, path)
    except Exception:
        endpoint_schema = "(unavailable)"
        common_errors = "(none)"

    prompt = FIX_ARGS_PROMPT.format(
        method=method,
        path=path,
        query_params=json.dumps(
            original_args.get("query_params"), indent=2, default=str
        ),
        body=json.dumps(original_args.get("body"), indent=2, default=str)[:2000],
        error_response=error_response[:2000],
        endpoint_schema=str(endpoint_schema)[:3000],
        common_errors=common_errors,
    )

    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = _extract_text(resp.content)
        parsed = _parse_json_object(raw)
        if parsed and isinstance(parsed, dict) and "method" in parsed:
            # Sanitize /v2 prefix from path
            if isinstance(parsed.get("path"), str) and parsed["path"].startswith(
                "/v2/"
            ):
                parsed["path"] = parsed["path"][3:]
            log.info("FIX_ARGS returned fixed args", fix=parsed)
            return parsed
    except Exception as e:
        log.warning(f"FIX_ARGS LLM call failed: {e}")

    return None


def _strip_v2_from_replan(parsed: dict):
    """Strip /v2 prefix from paths in replan/replace responses (base URL already has /v2)."""
    if parsed.get("action") == "retry":
        args = parsed.get("args", {})
        if isinstance(args.get("path"), str) and args["path"].startswith("/v2/"):
            args["path"] = args["path"][3:]
    elif parsed.get("action") == "replace":
        for s in parsed.get("steps", []):
            a = s.get("args", {})
            if isinstance(a.get("path"), str) and a["path"].startswith("/v2/"):
                a["path"] = a["path"][3:]


def _parse_json_object(raw: str) -> dict | None:
    """Extract a JSON object from LLM output (handles code blocks)."""
    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if code_match:
        raw = code_match.group(1)
    brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ────────────────────────────────────────────────────────────────────────────
# Recursive placeholder resolution
# ────────────────────────────────────────────────────────────────────────────


def _resolve_placeholders_deep(obj: Any, results: dict, llm) -> Any:
    """Recursively resolve $step_N placeholders in nested dicts, lists, and strings."""
    if isinstance(obj, str):
        return _resolve_placeholder(obj, results, llm)
    if isinstance(obj, dict):
        return {k: _resolve_placeholders_deep(v, results, llm) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_placeholders_deep(item, results, llm) for item in obj]
    return obj


def _resolve_placeholder(value: Any, results: dict, llm) -> Any:
    """Resolve $step_N.value.id (and similar) placeholders from previous results.

    Also handles ternary conditionals the LLM sometimes generates:
      $step_A.values.length > 0 ? $step_A.values[0].id : $step_B.value.id
    """
    if not isinstance(value, str):
        return value

    # Handle ternary conditional: $step_A.values.length > 0 ? $step_A... : $step_B...
    ternary = re.match(
        r"\$step_(\d+)\.values\.length\s*>\s*0\s*\?\s*"
        r"(\$step_\d+(?:[\.\[\w\]]+)*)\s*:\s*"
        r"(\$step_\d+(?:[\.\[\w\]]+)*)\s*$",
        value.strip(),
    )
    if ternary:
        check_step = f"step_{ternary.group(1)}"
        true_ref = ternary.group(2)
        false_ref = ternary.group(3)
        # Evaluate the condition: does step_A have non-empty values?
        check_result = results.get(check_step, {})
        values = (
            check_result.get("values", []) if isinstance(check_result, dict) else []
        )
        chosen = true_ref if values else false_ref
        log.info(
            f"Resolved ternary placeholder: chose {'true' if values else 'false'} branch → {chosen}"
        )
        return _resolve_placeholder(chosen, results, llm)

    # Handle OR fallback: "123 || $step_N.path" or "$step_N.path || 123"
    or_match = re.match(r"^\s*(.+?)\s*\|\|\s*(.+?)\s*$", value)
    if or_match:
        left, right = or_match.group(1), or_match.group(2)
        # Determine which side has a $step reference
        if "$step_" in right and "$step_" not in left:
            # "literal || $step_ref" — try the step ref first, fallback to literal
            resolved = _resolve_placeholder(right, results, llm)
            if resolved is _UNRESOLVED or resolved is None:
                log.info(f"OR fallback: step ref unresolved, using literal {left}")
                # Return as int if it looks like a number
                return int(left) if left.isdigit() else left
            log.info(f"OR fallback: resolved step ref → {resolved}")
            return resolved
        elif "$step_" in left and "$step_" not in right:
            # "$step_ref || literal" — try step ref first, fallback to literal
            resolved = _resolve_placeholder(left, results, llm)
            if resolved is _UNRESOLVED or resolved is None:
                log.info(f"OR fallback: step ref unresolved, using literal {right}")
                return int(right) if right.isdigit() else right
            log.info(f"OR fallback: resolved step ref → {resolved}")
            return resolved
        else:
            # Both have refs or neither — try left first
            resolved = _resolve_placeholder(left, results, llm)
            if resolved is not _UNRESOLVED and resolved is not None:
                return resolved
            return _resolve_placeholder(right, results, llm)

    pattern = r"\$step_(\d+)((?:[\.\[\w\]]+)*)"
    match = re.search(pattern, value)
    if not match:
        return value

    step_num = match.group(1)
    path_str = match.group(2)
    result_key = f"step_{step_num}"

    if result_key not in results:
        log.warning(f"Placeholder references missing result: {value}")
        return value

    obj = results[result_key]

    # Parse the path: supports .field and [N] indexing
    # e.g. ".value.id", ".values[0].id", ".value.orderLines[0].id"
    parts = re.findall(r"\.(\w+)|\[(\d+)\]", path_str)

    for field_part, index_part in parts:
        if field_part:
            if isinstance(obj, dict):
                obj = obj.get(field_part)
            elif isinstance(obj, list) and obj:
                # Legacy: if accessing .values on a list, treat as the list itself
                if field_part == "values" and isinstance(obj, list):
                    pass  # obj stays as the list
                else:
                    obj = obj[0].get(field_part) if isinstance(obj[0], dict) else None
            else:
                obj = None
                break
        elif index_part:
            idx = int(index_part)
            if isinstance(obj, list) and idx < len(obj):
                obj = obj[idx]
            else:
                log.warning(
                    f"Placeholder index [{idx}] out of bounds (list has {len(obj) if isinstance(obj, list) else 0} items) for {value}"
                )
                return _UNRESOLVED

    if obj is not None:
        # If the entire string is just the placeholder, return the resolved value directly
        if value == match.group(0):
            return obj
        # Otherwise replace inline
        return value.replace(match.group(0), str(obj))

    # Placeholder could not be resolved — return sentinel instead of expensive LLM fallback
    log.warning(f"Placeholder {value} could not be resolved from results")
    return _UNRESOLVED
