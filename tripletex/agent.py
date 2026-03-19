import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

from logger import get_logger
from prompts import SYSTEM_PROMPT
from tools import ALL_TOOLS

log = get_logger("tripletex.agent")


def build_agent():
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-001",
        google_api_key=os.environ["GOOGLE_API_KEY"],
        temperature=0,
    )
    agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SYSTEM_PROMPT,
    )
    return agent


def _log_agent_messages(messages: list) -> None:
    """Log the full agent reasoning chain for debugging."""
    log.info("--- Agent message trace ---")
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            log.info(f"[{i}] HumanMessage", content=content[:500])

        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    log.info(
                        f"[{i}] AIMessage → tool call: {tc['name']}",
                        tool=tc["name"],
                        args=tc["args"],
                    )
            else:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                log.info(f"[{i}] AIMessage (final)", content=content[:1000])

        elif isinstance(msg, ToolMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            log.info(
                f"[{i}] ToolMessage ← {msg.name}",
                tool=msg.name,
                result=content[:500],
            )

        else:
            log.info(f"[{i}] {type(msg).__name__}", content=str(msg)[:300])

    log.info("--- End of message trace ---")


def run_agent(agent, prompt: str, file_context: str = "") -> None:
    user_message = prompt
    if file_context:
        user_message = f"{prompt}\n\n--- Attached Files ---\n{file_context}"

    log.info("Invoking agent", prompt_length=len(user_message))

    result = agent.invoke({"messages": [{"role": "user", "content": user_message}]})

    _log_agent_messages(result.get("messages", []))
