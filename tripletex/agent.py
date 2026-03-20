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
from prompts import FIX_ARGS_PROMPT, PLANNER_PROMPT, PLANNER_PROFILE, REPLAN_PROMPT
from state import AgentState
from tools import load_tools

log = get_logger("tripletex.agent")

# Sentinel for unresolved $step_N placeholders (empty search results, etc.)
_UNRESOLVED = "__UNRESOLVED__"

MAX_REPLANS = 2  # max replan attempts per invocation


def validate_plan(plan: list[dict]) -> list[dict]:
    """Validate and auto-fix plan steps against endpoint cards.

    Catches cheapest errors before they hit the API:
    - Prepends bank account registration when plan involves invoicing
    - Adds missing required fields with defaults
    - Removes conflicting fields
    - Strips product "number" field from POST /product/list
    - Strips inline costs/perDiems from POST /travelExpense
    - Prepends GET /travelExpense/paymentType when plan has travel costs without paymentType
    - Validates enum values
    """
    try:
        from endpoint_catalog import ENDPOINT_CARDS
    except ImportError:
        return plan

    # Check if plan involves invoicing (/:invoice action or POST /invoice)
    needs_bank_account = False
    for step in plan:
        if step.get("tool_name") != "call_api":
            continue
        args = step.get("args", {})
        path = args.get("path", "")
        method = args.get("method", "")
        if "/:invoice" in path or (method == "POST" and "/invoice" in path):
            needs_bank_account = True
            break

    # Check if plan has travel expense costs but no paymentType lookup
    has_travel_cost = False
    has_payment_type_lookup = False
    for step in plan:
        if step.get("tool_name") != "call_api":
            continue
        args = step.get("args", {})
        path = args.get("path", "")
        method = args.get("method", "")
        if method == "POST" and "/travelExpense/cost" in path:
            has_travel_cost = True
        if method == "GET" and "/travelExpense/paymentType" in path:
            has_payment_type_lookup = True

    if needs_bank_account:
        # Prepend: ensure_bank_account meta-step that the executor handles specially.
        # This avoids wasting an API call if the bank account already exists.
        bank_step = {
            "step_number": 1,
            "tool_name": "ensure_bank_account",
            "args": {},
            "description": "Ensure company has a bank account registered (required for invoicing)",
        }

        # Renumber existing steps
        for step in plan:
            step["step_number"] += 1
            _shift_step_refs(step, offset=1)

        plan = [bank_step] + plan
        log.info("Validation: prepended ensure_bank_account step for invoicing")

    # Inject GET /travelExpense/paymentType before first travel cost if missing
    if has_travel_cost and not has_payment_type_lookup:
        # Find the first travel cost step
        first_cost_idx = None
        for i, step in enumerate(plan):
            if step.get("tool_name") != "call_api":
                continue
            args = step.get("args", {})
            if args.get("method") == "POST" and "/travelExpense/cost" in args.get("path", ""):
                first_cost_idx = i
                break

        if first_cost_idx is not None:
            # Insert a GET paymentType step right before the first cost step
            pt_step_number = plan[first_cost_idx]["step_number"]
            pt_step = {
                "step_number": pt_step_number,
                "tool_name": "call_api",
                "args": {
                    "method": "GET",
                    "path": "/travelExpense/paymentType",
                    "query_params": {"showOnEmployeeExpenses": True, "count": 1, "fields": "id"},
                },
                "description": "Get travel expense payment type (required for costs)",
            }

            # Renumber steps from first_cost_idx onward
            for step in plan[first_cost_idx:]:
                step["step_number"] += 1
                _shift_step_refs(step, offset=1)

            plan.insert(first_cost_idx, pt_step)

            # Inject paymentType reference into all travel cost bodies
            pt_ref = f"$step_{pt_step_number}.values[0].id"
            for step in plan[first_cost_idx + 1:]:
                if step.get("tool_name") != "call_api":
                    continue
                args = step.get("args", {})
                if args.get("method") == "POST" and "/travelExpense/cost" in args.get("path", ""):
                    body = args.get("body", {})
                    if isinstance(body, dict) and "paymentType" not in body:
                        body["paymentType"] = {"id": pt_ref}

            log.info("Validation: injected GET /travelExpense/paymentType step and paymentType refs for travel costs")

    # ── A3: Strip unnecessary GET /ledger/vatType lookups for known IDs ──
    KNOWN_VAT_IDS = {"1": 1, "3": 3, "5": 5, "6": 6, "33": 33}
    vat_steps_to_remove = []  # indices to remove
    for i, step in enumerate(plan):
        if step.get("tool_name") != "call_api":
            continue
        args = step.get("args", {})
        if args.get("method") == "GET" and "/ledger/vatType" in args.get("path", ""):
            qp = args.get("query_params", {})
            vat_num = str(qp.get("number", ""))
            if vat_num in KNOWN_VAT_IDS:
                known_id = KNOWN_VAT_IDS[vat_num]
                step_num = step["step_number"]
                ref_pattern = f"$step_{step_num}.values[0].id"
                # Replace all references in subsequent steps
                _replace_ref_in_plan(plan, ref_pattern, known_id)
                vat_steps_to_remove.append(i)
                log.info(f"Validation: stripped GET /ledger/vatType?number={vat_num}, using known ID {known_id}")

    # Remove vatType lookup steps (reverse order to preserve indices)
    for idx in reversed(vat_steps_to_remove):
        plan.pop(idx)

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

    if has_employee_post and not has_department_in_plan and employee_post_idx is not None:
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
        # Renumber from employee_post_idx onward
        for step in plan[employee_post_idx:]:
            step["step_number"] += 1
            _shift_step_refs(step, offset=1)
        plan.insert(employee_post_idx, dept_step)

        # Inject department ref into employee body
        emp_step = plan[employee_post_idx + 1]
        emp_body = emp_step.get("args", {}).get("body", {})
        if isinstance(emp_body, dict) and "department" not in emp_body:
            emp_body["department"] = {"id": f"$step_{dept_step_number}.values[0].id"}
        log.info("Validation: injected GET /department step and department ref for POST /employee")

    for step in plan:
        if step.get("tool_name") != "call_api":
            continue
        args = step.get("args", {})
        method = args.get("method", "")
        path = args.get("path", "")
        body = args.get("body", {})
        query_params = args.get("query_params", {})

        # ── B1: Fix fields filter dot→parentheses ──
        if method == "GET" and isinstance(query_params, dict):
            fields_val = query_params.get("fields", "")
            if isinstance(fields_val, str) and "." in fields_val:
                # Convert e.g. "orders.orderLines.description" → "orders(orderLines(description))"
                fixed = _fix_fields_dots(fields_val)
                if fixed != fields_val:
                    query_params["fields"] = fixed
                    log.info(f"Validation: fixed fields filter dots→parentheses: {fields_val} → {fixed}")

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
                    log.info(f"Validation: POST /project has projectManager ref {pm_id}")

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
                log.info("Validation: converted null postings to empty array in POST /ledger/voucher")
            # Add explicit row numbers starting from 1 (row 0 is reserved for system-generated VAT lines)
            postings = body.get("postings", [])
            if isinstance(postings, list):
                for idx, posting in enumerate(postings):
                    if isinstance(posting, dict) and "row" not in posting:
                        posting["row"] = idx + 1
                        log.info(f"Validation: added row={idx+1} to voucher posting")

        # Quick fix: strip product "number" field from POST /product or /product/list
        if method == "POST" and path in ("/product", "/product/list"):
            if isinstance(body, list):
                for item in body:
                    if isinstance(item, dict) and "number" in item:
                        del item["number"]
                        log.info("Validation: stripped 'number' from product in POST /product/list")
            elif isinstance(body, dict) and "number" in body:
                del body["number"]
                log.info("Validation: stripped 'number' from POST /product body")

        # Quick fix: strip inline costs/perDiems from POST /travelExpense
        if method == "POST" and path == "/travelExpense" and isinstance(body, dict):
            for inline_field in ("costs", "perDiemCompensations"):
                if inline_field in body:
                    del body[inline_field]
                    log.info(f"Validation: stripped inline '{inline_field}' from POST /travelExpense")

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
                    log.info(f"Validation: added missing {field_name}={default} to {key}")
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
                                log.info(f"Validation: removed conflicting {f} from {field_name} item in {key}")

        # Check 3: Validate enum values (log warning only)
        for field_name, field_info in card.get("fields", {}).items():
            if "enum" in field_info and field_name in body:
                val = body[field_name]
                if isinstance(val, str) and not val.startswith("$step_") and val not in field_info["enum"]:
                    log.warning(f"Validation: {field_name}={val} not in {field_info['enum']}")

    return plan


def _path_to_template(path: str) -> str:
    """Convert /customer/123 → /customer/{id}, /order/456/:invoice → /order/{id}/:invoice"""
    return re.sub(r'/(\d+)', '/{id}', path)


def _ensure_bank_account(call_api_tool, error_count: int) -> tuple[str, dict, int]:
    """Ensure the company has a bank account registered.

    Searches for existing bank accounts first; only creates one if none found.
    Returns (result_str, parsed, error_count).
    """
    # Step 1: Check for existing bank account
    search_result = call_api_tool.invoke({
        "method": "GET",
        "path": "/ledger/account",
        "query_params": {"isBankAccount": True, "from": 0, "count": 1, "fields": "id,number,bankAccountNumber"},
    })

    try:
        parsed = json.loads(search_result)
        values = parsed.get("values", [])
        if values:
            log.info(f"Bank account already exists: account {values[0].get('number', '?')}")
            return search_result, parsed, error_count
    except (json.JSONDecodeError, TypeError):
        pass

    # Step 2: No bank account found — create one (account 1920 = standard Norwegian bank account)
    log.info("No bank account found, creating account 1920")
    create_result = call_api_tool.invoke({
        "method": "POST",
        "path": "/ledger/account",
        "body": {
            "number": 1920,
            "name": "Bankkonto",
            "isBankAccount": True,
            "bankAccountNumber": "12345678903",
        },
    })

    try:
        parsed = json.loads(create_result)
        status = parsed.get("status", 0)
        if isinstance(status, int) and status >= 400:
            log.warning(f"Failed to create bank account: {create_result[:500]}")
            error_count += 1
        else:
            log.info("Bank account 1920 created successfully")
    except (json.JSONDecodeError, TypeError):
        parsed = {"raw": create_result}

    return create_result, parsed, error_count


def _shift_step_refs(obj, offset: int):
    """Shift all $step_N references in a plan step by offset (in-place mutation)."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                obj[k] = re.sub(
                    r'\$step_(\d+)',
                    lambda m: f'$step_{int(m.group(1)) + offset}',
                    v,
                )
            else:
                _shift_step_refs(v, offset)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                obj[i] = re.sub(
                    r'\$step_(\d+)',
                    lambda m: f'$step_{int(m.group(1)) + offset}',
                    item,
                )
            else:
                _shift_step_refs(item, offset)

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
                log.info(f"Validation: bumped {to_key} from {to_val} to {new_to} (must be > {from_key})")
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

        # Penalty: unnecessary vatType lookup for known IDs
        if method == "GET" and "/ledger/vatType" in path:
            vat_num = str(qp.get("number", ""))
            if vat_num in ("1", "3", "5", "6", "33"):
                score -= 5  # known ID, no lookup needed

        # Penalty: unnecessary paymentType lookup
        if method == "GET" and "/invoice/paymentType" in path:
            score -= 5

        # Bonus: employee dedup check
        if method == "GET" and path == "/employee":
            score += 10
        if method == "POST" and "/employee" in path:
            # Check if there's a GET /employee in the plan
            has_emp_get = any(
                s.get("args", {}).get("method") == "GET"
                and s.get("args", {}).get("path") == "/employee"
                for s in plan if s.get("tool_name") == "call_api"
            )
            if not has_emp_get:
                score -= 10

        # Penalty: product "number" field
        if path in ("/product", "/product/list"):
            items = body if isinstance(body, list) else [body]
            if any("number" in item for item in items if isinstance(item, dict)):
                score -= 15

        # Penalty: travel expense with inline costs
        if isinstance(body, dict) and path == "/travelExpense":
            if "costs" in body or "perDiemCompensations" in body:
                score -= 20

    return score



def build_agent():
    """Build the planner/executor StateGraph."""
    tools, tool_summaries = load_tools()
    tool_map = {t.name: t for t in tools}

    default_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    llm = ChatGoogleGenerativeAI(
        model=default_model,
        google_api_key=os.environ["GOOGLE_API_KEY"],
        temperature=0,
    )

    # --- Node: planner (single efficient profile) ---
    def planner(state: AgentState) -> dict:
        prompt_text = PLANNER_PROMPT.format(
            today=date.today().isoformat(),
            tool_summaries=tool_summaries,
            task=state["original_prompt"],
        )

        full_prompt = PLANNER_PROFILE["prefix"] + "\n\n" + prompt_text
        log.info("Planner invoked", prompt_length=len(full_prompt))

        try:
            response = llm.invoke([HumanMessage(content=full_prompt)])
            raw = _extract_text(response.content)
            best = _parse_plan_json(raw)
            log.info(f"Planner returned {len(best)} steps", output=raw[:1000])
        except Exception as e:
            log.warning(f"Planner failed: {e}")
            best = []

        score = _score_plan(best, state["original_prompt"])
        best = validate_plan(best)

        log.info(
            f">>>PLAN_START<<<\n{json.dumps(best, indent=2)}\n>>>PLAN_END<<<",
            steps=len(best),
            score=score,
        )

        return {
            "plan": best,
            "current_step": 0,
            "results": {},
            "completed_steps": [],
            "error_count": state.get("error_count", 0),
            "replan_count": 0,
            "messages": [AIMessage(content=f"Plan (efficient): {json.dumps(best)}")],
        }

    # --- Node: executor ---
    def executor(state: AgentState) -> dict:
        plan = state["plan"]
        step_idx = state["current_step"]
        results = dict(state.get("results", {}))
        error_count = state.get("error_count", 0)
        replan_count = state.get("replan_count", 0)
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
                    "replan_count": replan_count,
                    "messages": [AIMessage(content=f"Step {step['step_number']} done: bank account ensured")],
                }

        # Resolve $step_N placeholders recursively through nested dicts/lists
        resolved_args = _resolve_placeholders_deep(args, results, llm)

        # Skip steps with unresolved dependencies (e.g. empty search results)
        if _contains_unresolved(resolved_args):
            log.warning(f"Step {step['step_number']} skipped: unresolved dependency from previous step")
            results[f"step_{step['step_number']}"] = {"skipped": True, "reason": "unresolved_dependency"}
            completed.append(step["step_number"])
            return {
                "current_step": step_idx + 1,
                "results": results,
                "error_count": error_count,
                "replan_count": replan_count,
                "completed_steps": completed,
                "messages": [AIMessage(content=f"Step {step['step_number']} skipped: dependency unresolved")],
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
                "replan_count": replan_count,
                "completed_steps": completed,
                "messages": [AIMessage(content=f"Error: {error_msg}")],
            }

        tool = tool_map[tool_name]

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
                "replan_count": replan_count,
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
            log.info(f"Step {step['step_number']} completed", result_preview=str(parsed)[:500])
            completed.append(step["step_number"])
            return {
                "current_step": step_idx + 1,
                "results": results,
                "completed_steps": completed,
                "error_count": error_count,
                "replan_count": replan_count,
                "messages": [AIMessage(content=f"Step {step['step_number']} done: {str(parsed)[:200]}")],
            }

        # API error — use adaptive self-heal (replan)
        if status_code in RETRYABLE_STATUS_CODES and replan_count < MAX_REPLANS:
            log.warning(f"API error {status_code}, attempting adaptive replan ({replan_count+1}/{MAX_REPLANS})")

            replan_result = _ask_llm_to_replan(
                llm, resolved_args, result_str,
                plan[step_idx + 1:],  # remaining steps
                results,
                state["original_prompt"],
                step["step_number"] + 1,
            )

            if replan_result and replan_result.get("action") == "retry":
                # Retry with fixed args
                fixed_args = replan_result.get("args", {})
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
                    log.info(f"Step {step['step_number']} succeeded after retry")
                    completed.append(step["step_number"])
                    return {
                        "current_step": step_idx + 1,
                        "results": results,
                        "completed_steps": completed,
                        "error_count": error_count,
                        "replan_count": replan_count + 1,
                        "messages": [AIMessage(content=f"Step {step['step_number']} done (retried): {str(parsed)[:200]}")],
                    }
                else:
                    # Retry also failed — count 1 error, move on
                    log.warning(f"Retry also failed with status {retry_status}")
                    _log_self_heal(tool.name, resolved_args, result_str, fixed_args, retry_succeeded=False)
                    try:
                        parsed = json.loads(retry_result_str)
                    except (json.JSONDecodeError, TypeError):
                        parsed = {"raw": retry_result_str}
                    results[f"step_{step['step_number']}"] = parsed
                    error_count += 1
                    completed.append(step["step_number"])
                    return {
                        "current_step": step_idx + 1,
                        "results": results,
                        "completed_steps": completed,
                        "error_count": error_count,
                        "replan_count": replan_count + 1,
                        "messages": [AIMessage(content=f"Step {step['step_number']} failed after retry")],
                    }

            elif replan_result and replan_result.get("action") == "skip":
                # Skip this step
                reason = replan_result.get("reason", "replan decided to skip")
                log.info(f"Replan: skipping step {step['step_number']} — {reason}")
                results[f"step_{step['step_number']}"] = {"skipped": True, "reason": reason}
                completed.append(step["step_number"])
                return {
                    "current_step": step_idx + 1,
                    "results": results,
                    "completed_steps": completed,
                    "error_count": error_count + 1,  # the original error still counts
                    "replan_count": replan_count + 1,
                    "messages": [AIMessage(content=f"Step {step['step_number']} skipped by replan: {reason}")],
                }

            elif replan_result and replan_result.get("action") == "replace":
                # Replace remaining plan with new steps
                new_steps = replan_result.get("steps", [])
                log.info(f"Replan: replacing step {step['step_number']} + remaining with {len(new_steps)} new steps")
                # Keep completed steps, splice in new steps
                new_plan = plan[:step_idx] + new_steps
                results[f"step_{step['step_number']}"] = {"skipped": True, "reason": "replaced by replan"}
                completed.append(step["step_number"])
                return {
                    "plan": new_plan,
                    "current_step": step_idx + 1 if not new_steps else step_idx,
                    "results": results,
                    "completed_steps": completed,
                    "error_count": error_count + 1,
                    "replan_count": replan_count + 1,
                    "messages": [AIMessage(content=f"Step {step['step_number']} replaced by replan ({len(new_steps)} new steps)")],
                }
        elif status_code not in RETRYABLE_STATUS_CODES:
            log.warning(f"API error {status_code} — not retryable, skipping self-heal")

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
            "replan_count": replan_count,
            "messages": [AIMessage(content=f"Step {step['step_number']} failed: {str(parsed)[:200]}")],
        }

    # --- Node: check_done ---
    def check_done(state: AgentState) -> str:
        if state["current_step"] >= len(state["plan"]):
            log.info("All steps completed")
            return "end"
        if state.get("error_count", 0) >= 3:
            log.warning("Too many errors, aborting to preserve efficiency score")
            return "end"
        return "continue"

    # Build graph
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner)
    graph.add_node("executor", executor)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "executor")
    graph.add_conditional_edges(
        "executor",
        check_done,
        {"continue": "executor", "end": END},
    )

    return graph.compile()


def run_agent(agent, prompt: str, file_context: str = "") -> None:
    """Run the agent with the given prompt."""
    user_message = prompt
    if file_context:
        user_message = f"{prompt}\n\n--- Attached Files ---\n{file_context}"

    log.info("Invoking agent", prompt_length=len(user_message))

    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "plan": [],
        "current_step": 0,
        "results": {},
        "completed_steps": [],
        "error_count": 0,
        "replan_count": 0,
        "original_prompt": user_message,
    }

    result = agent.invoke(initial_state)

    # Log final state
    completed = result.get("completed_steps", [])
    errors = result.get("error_count", 0)
    replans = result.get("replan_count", 0)
    log.info(
        "Agent finished",
        completed_steps=len(completed),
        total_steps=len(result.get("plan", [])),
        errors=errors,
        replans=replans,
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
        from generic_tools import get_endpoint_schema
        endpoint_schema = get_endpoint_schema(method, path)
    except Exception:
        endpoint_schema = "(unavailable)"

    # Format remaining steps and previous results compactly
    remaining_str = json.dumps(remaining_steps, indent=2, default=str)[:2000] if remaining_steps else "[]"
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
            log.info(f"Replan decision: {parsed.get('action')}", replan=parsed)
            return parsed
    except Exception as e:
        log.warning(f"Replan LLM call failed: {e}")

    return None


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
        values = check_result.get("values", []) if isinstance(check_result, dict) else []
        chosen = true_ref if values else false_ref
        log.info(f"Resolved ternary placeholder: chose {'true' if values else 'false'} branch → {chosen}")
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
                log.warning(f"Index [{idx}] out of bounds (list length {len(obj) if isinstance(obj, list) else 'N/A'})")
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
