"""LangGraph state schema for the Tripletex planner/executor agent."""

from typing import Any, Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class PlanStep(TypedDict):
    step_number: int
    tool_name: str
    args: dict  # may contain "$step_N.value.id" placeholders
    description: str


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    plan: list[PlanStep]
    current_step: int
    results: dict[str, Any]  # "step_1" -> parsed JSON response
    completed_steps: list[int]
    error_count: int
    healed_steps: list[int]  # step numbers that already used FIX_ARGS
    original_prompt: str
    file_content_parts: list[dict]  # multimodal file parts for planner LLM calls
    deadline: float  # time.monotonic() deadline — skip verifier if past this
    verification_attempts: int
