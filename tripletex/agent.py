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
from prompts import EXECUTOR_FALLBACK_PROMPT, FIX_ARGS_PROMPT, PLANNER_PROMPT
from state import AgentState
from tools import load_tools

log = get_logger("tripletex.agent")


def build_agent():
    """Build the planner/executor StateGraph."""
    tools, tool_summaries = load_tools()
    tool_map = {t.name: t for t in tools}

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro",
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
        raw = response.content if isinstance(response.content, str) else str(response.content)

        log.info("Planner raw output", output=raw[:2000])

        # Parse JSON from response (handle markdown code blocks)
        plan = _parse_plan_json(raw)

        log.info(
            ">>>PLAN_START<<<\n"
            f"{json.dumps(plan, indent=2)}\n"
            ">>>PLAN_END<<<",
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
        args = dict(step.get("args", {}))
        description = step.get("description", f"Step {step['step_number']}")

        log.info(
            f"Executing step {step['step_number']}: {description}",
            tool=tool_name,
            tool_args=args,
        )

        # Resolve $step_N placeholders
        resolved_args = {}
        for k, v in args.items():
            resolved_args[k] = _resolve_placeholder(v, results, llm)

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
            "messages": [AIMessage(content=f"Step {step['step_number']} done: {str(parsed)[:200]}")],
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


def _is_api_error(result_str: str) -> bool:
    """Check if the API response indicates a 4xx/5xx error."""
    try:
        parsed = json.loads(result_str)
        status = parsed.get("status", 0)
        return isinstance(status, int) and status >= 400
    except (json.JSONDecodeError, TypeError):
        return False


def _log_self_heal(tool_name: str, original_args: dict, error_response: str, fixed_args: dict | None, retry_succeeded: bool) -> None:
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


def _ask_llm_to_fix_args(
    llm, tool, original_args: dict, error_response: str
) -> dict | None:
    """Ask the LLM to fix tool arguments based on the API error. Returns fixed args or None."""
    schema = tool.args_schema.model_json_schema() if tool.args_schema else {}
    params_summary = json.dumps(schema.get("properties", {}), indent=2)[:2000]

    prompt = FIX_ARGS_PROMPT.format(
        tool_name=tool.name,
        tool_args=json.dumps(original_args, indent=2, default=str),
        error_response=error_response[:2000],
        tool_description=tool.description,
        tool_params=params_summary,
    )

    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = resp.content if isinstance(resp.content, str) else str(resp.content)
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


def _call_tool_with_retry(tool, resolved_args: dict, llm, error_count: int) -> tuple[str, dict, int]:
    """Call a tool, and if it returns a 4xx/5xx, ask the LLM to fix args and retry once.

    Returns (result_str, parsed_result, updated_error_count).
    """
    for attempt in range(1 + MAX_RETRIES):
        try:
            result_str = tool.invoke(resolved_args)
        except Exception as e:
            error_msg = f"Tool {tool.name} raised: {str(e)}"
            log.error(error_msg)
            return error_msg, {"error": error_msg}, error_count + 1

        if not _is_api_error(result_str):
            # Success
            try:
                parsed = json.loads(result_str)
            except (json.JSONDecodeError, TypeError):
                parsed = {"raw": result_str}
            return result_str, parsed, error_count

        # API error — try self-heal on first attempt only
        if attempt < MAX_RETRIES:
            log.warning(
                f"API error from {tool.name}, attempting self-heal",
                attempt=attempt + 1,
            )
            fixed_args = _ask_llm_to_fix_args(llm, tool, resolved_args, result_str)
            if fixed_args:
                _log_self_heal(tool.name, resolved_args, result_str, fixed_args, retry_succeeded=True)
                resolved_args = fixed_args
                continue
            else:
                _log_self_heal(tool.name, resolved_args, result_str, None, retry_succeeded=False)

        # Out of retries or LLM couldn't fix — return the error
        if attempt == MAX_RETRIES:
            # Log that the retry also failed
            _log_self_heal(tool.name, resolved_args, result_str, resolved_args, retry_succeeded=False)
        log.warning(f"Tool {tool.name} failed after {attempt + 1} attempt(s)")
        try:
            parsed = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            parsed = {"raw": result_str}
        return result_str, parsed, error_count + 1

    # Should not reach here, but just in case
    return result_str, {"raw": result_str}, error_count + 1


def _resolve_placeholder(value: Any, results: dict, llm) -> Any:
    """Resolve $step_N.value.id (and similar) placeholders from previous results."""
    if not isinstance(value, str):
        return value

    pattern = r"\$step_(\d+)((?:\.\w+)*)"
    match = re.search(pattern, value)
    if not match:
        return value

    step_num = match.group(1)
    path_parts = [p for p in match.group(2).split(".") if p]
    result_key = f"step_{step_num}"

    if result_key not in results:
        log.warning(f"Placeholder references missing result: {value}")
        return value

    obj = results[result_key]

    # Navigate the path
    for part in path_parts:
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list) and obj:
            # For list results (search), take first item then continue
            obj = obj[0] if part == "values" else obj[0].get(part) if isinstance(obj[0], dict) else None
        else:
            obj = None
            break

    if obj is not None:
        # If the entire string is just the placeholder, return the resolved value directly
        if value == match.group(0):
            return obj
        # Otherwise replace inline
        return value.replace(match.group(0), str(obj))

    # Fallback: use LLM to extract
    log.info(f"Using LLM fallback to resolve: {value}")
    try:
        fallback_prompt = EXECUTOR_FALLBACK_PROMPT.format(
            response=json.dumps(results[result_key])[:2000],
            description=f"Extract value for path: {'.'.join(path_parts)} (from placeholder {value})",
        )
        resp = llm.invoke([HumanMessage(content=fallback_prompt)])
        extracted = resp.content.strip() if isinstance(resp.content, str) else str(resp.content).strip()
        # Try to convert to int if it looks like an ID
        try:
            return int(extracted)
        except ValueError:
            return extracted
    except Exception as e:
        log.error(f"LLM fallback failed for {value}: {e}")
        return value
