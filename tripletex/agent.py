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
from prompts import EXECUTOR_FALLBACK_PROMPT, PLANNER_PROMPT
from state import AgentState
from tools import load_tools

log = get_logger("tripletex.agent")


def build_agent():
    """Build the planner/executor StateGraph."""
    tools, tool_summaries = load_tools()
    tool_map = {t.name: t for t in tools}

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
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

        log.info("Plan parsed", steps=len(plan), plan=json.dumps(plan, indent=2)[:2000])

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

        try:
            result_str = tool_map[tool_name].invoke(resolved_args)
        except Exception as e:
            error_msg = f"Tool {tool_name} failed: {str(e)}"
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

        # Parse result
        try:
            parsed = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            parsed = {"raw": result_str}

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
