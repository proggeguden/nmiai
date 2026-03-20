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
from prompts import FIX_ARGS_PROMPT, PLANNER_PROMPT
from state import AgentState
from tools import load_tools

log = get_logger("tripletex.agent")

# Sentinel for unresolved $step_N placeholders (empty search results, etc.)
_UNRESOLVED = "__UNRESOLVED__"


def validate_plan(plan: list[dict]) -> list[dict]:
    """Validate and auto-fix plan steps against endpoint cards.

    Catches cheapest errors before they hit the API:
    - Prepends bank account registration when plan involves invoicing
    - Adds missing required fields with defaults
    - Removes conflicting fields
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

    for step in plan:
        if step.get("tool_name") != "call_api":
            continue
        args = step.get("args", {})
        method = args.get("method", "")
        path = args.get("path", "")
        body = args.get("body", {})
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


def build_agent():
    """Build the planner/executor StateGraph."""
    tools, tool_summaries = load_tools()
    tool_map = {t.name: t for t in tools}

    llm = ChatGoogleGenerativeAI(
        model=os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview"),
        google_api_key=os.environ["GOOGLE_API_KEY"],
        temperature=0,
    )

    # --- Node: planner ---
    def planner(state: AgentState) -> dict:
        prompt_text = PLANNER_PROMPT.format(
            today=date.today().isoformat(),
            tool_summaries=tool_summaries,
            task=state["original_prompt"],
        )

        log.info("Planner invoked", prompt_length=len(prompt_text))

        response = llm.invoke([HumanMessage(content=prompt_text)])
        raw = _extract_text(response.content)

        log.info("Planner raw output", output=raw[:2000])

        # Parse JSON from response (handle markdown code blocks)
        plan = _parse_plan_json(raw)
        plan = validate_plan(plan)

        log.info(
            f">>>PLAN_START<<<\n{json.dumps(plan, indent=2)}\n>>>PLAN_END<<<",
            steps=len(plan),
        )

        return {
            "plan": plan,
            "current_step": 0,
            "results": {},
            "completed_steps": [],
            "error_count": state.get("error_count", 0),
            "messages": [AIMessage(content=f"Plan: {json.dumps(plan)}")],
        }

    # --- Node: executor ---
    def executor(state: AgentState) -> dict:
        plan = state["plan"]
        step_idx = state["current_step"]
        results = dict(state.get("results", {}))
        error_count = state.get("error_count", 0)
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
                "completed_steps": completed,
                "messages": [AIMessage(content=f"Error: {error_msg}")],
            }

        tool = tool_map[tool_name]
        result_str, parsed, error_count = _call_tool_with_retry(
            tool, resolved_args, llm, error_count
        )

        results[f"step_{step['step_number']}"] = parsed

        log.info(
            f"Step {step['step_number']} completed",
            tool=tool_name,
            result_preview=str(parsed)[:500],
        )

        completed.append(step["step_number"])
        return {
            "current_step": step_idx + 1,
            "results": results,
            "completed_steps": completed,
            "error_count": error_count,
            "messages": [
                AIMessage(
                    content=f"Step {step['step_number']} done: {str(parsed)[:200]}"
                )
            ],
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
        "original_prompt": user_message,
    }

    result = agent.invoke(initial_state)

    # Log final state
    completed = result.get("completed_steps", [])
    errors = result.get("error_count", 0)
    log.info(
        "Agent finished",
        completed_steps=len(completed),
        total_steps=len(result.get("plan", [])),
        errors=errors,
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


MAX_RETRIES = 1  # one retry after LLM fix — keeps total API errors to 1 per step


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


def _ask_llm_to_fix_args(llm, original_args: dict, error_response: str) -> dict | None:
    """Ask the LLM to fix call_api arguments based on the API error. Returns fixed args or None."""
    # Extract method/path from the call_api args
    method = original_args.get("method", "POST")
    path = original_args.get("path", "")
    query_params = original_args.get("query_params", {})
    body = original_args.get("body", {})

    # Get endpoint schema for rich context
    try:
        from generic_tools import get_endpoint_schema

        endpoint_schema = get_endpoint_schema(method, path)
    except Exception:
        endpoint_schema = "(unavailable)"

    prompt = FIX_ARGS_PROMPT.format(
        method=method,
        path=path,
        query_params=json.dumps(query_params, indent=2, default=str)
        if query_params
        else "{}",
        body=json.dumps(body, indent=2, default=str) if body else "{}",
        error_response=error_response[:2000],
        endpoint_schema=endpoint_schema[:3000],
    )

    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = _extract_text(resp.content)
        fixed = _parse_json_object(raw)
        if fixed and isinstance(fixed, dict):
            log.info("LLM suggested fixed args", fixed_args=fixed)
            return fixed
    except Exception as e:
        log.warning(f"LLM fix-args call failed: {e}")

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


def _call_tool_with_retry(
    tool, resolved_args: dict, llm, error_count: int
) -> tuple[str, dict, int]:
    """Call a tool, and if it returns a retryable error (400/422), ask the LLM to fix args and retry once.

    Non-retryable errors (401, 403, 404, 409, 5xx) are returned immediately without retry.

    Returns (result_str, parsed_result, updated_error_count).
    """
    for attempt in range(1 + MAX_RETRIES):
        try:
            result_str = tool.invoke(resolved_args)
        except Exception as e:
            error_msg = f"Tool {tool.name} raised: {str(e)}"
            log.error(error_msg)
            return error_msg, {"error": error_msg}, error_count + 1

        is_error, status_code = _is_api_error(result_str)

        if not is_error:
            # Success
            try:
                parsed = json.loads(result_str)
            except (json.JSONDecodeError, TypeError):
                parsed = {"raw": result_str}
            return result_str, parsed, error_count

        # API error — only retry on retryable status codes
        if attempt < MAX_RETRIES and status_code in RETRYABLE_STATUS_CODES:
            log.warning(
                f"API error {status_code} from {tool.name}, attempting self-heal",
                attempt=attempt + 1,
            )
            fixed_args = _ask_llm_to_fix_args(llm, resolved_args, result_str)
            if fixed_args:
                _log_self_heal(
                    tool.name,
                    resolved_args,
                    result_str,
                    fixed_args,
                    retry_succeeded=True,
                )
                resolved_args = fixed_args
                continue
            else:
                _log_self_heal(
                    tool.name, resolved_args, result_str, None, retry_succeeded=False
                )
        elif attempt < MAX_RETRIES and status_code not in RETRYABLE_STATUS_CODES:
            log.warning(
                f"API error {status_code} from {tool.name} — not retryable, skipping self-heal",
            )

        # Out of retries or non-retryable — return the error
        log.warning(
            f"Tool {tool.name} failed with status {status_code} after {attempt + 1} attempt(s)"
        )
        try:
            parsed = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            parsed = {"raw": result_str}
        return result_str, parsed, error_count + 1

    # Should not reach here, but just in case
    return result_str, {"raw": result_str}, error_count + 1


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
    """Resolve $step_N.value.id (and similar) placeholders from previous results."""
    if not isinstance(value, str):
        return value

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
