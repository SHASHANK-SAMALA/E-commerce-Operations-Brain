"""create_react_agent — ReAct agent factory built on LangGraph StateGraph.

langgraph-prebuilt 1.1.0 ships chat_agent_executor.py but the file is not
written to disk due to a namespace-package collision with langgraph 1.2.2.
This module reimplements the same factory from first principles so the
rest of the codebase can import it with a stable path.

Usage
-----
    agent = create_react_agent(llm, tools=mcp_tools, system_prompt="...")
    result = await agent.ainvoke({"messages": [HumanMessage(content="...")]})
    # result["messages"][-1] is the final AIMessage with the agent's answer
"""

from __future__ import annotations

import asyncio
import json

import structlog
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, MessagesState, StateGraph

from ecommerce_brain.guardrails.prompt_injection import InjectionDetected, check_for_injection

log = structlog.get_logger(__name__)

# Maximum number of tool-call rounds before the agent is forced to conclude.
# Exported so domain_agents.py can import it rather than redefine the same constant.
MAX_ITERATIONS = 5


def create_react_agent(
    llm,
    tools: list[BaseTool],
    *,
    system_prompt: str = "",
    max_iterations: int = MAX_ITERATIONS,
):
    """Build and compile a ReAct agent graph.

    Parameters
    ----------
    llm:
        Any LangChain chat model (sync or async).
    tools:
        List of LangChain-compatible tool objects (e.g. from MCP).
    system_prompt:
        Optional system message prepended to every conversation.
    max_iterations:
        Hard cap on tool-call rounds. Prevents runaway loops.

    Returns
    -------
    A compiled LangGraph ``StateGraph`` whose input/output schema is
    ``MessagesState`` — i.e. ``{"messages": list[BaseMessage]}``.
    """
    tool_map: dict[str, BaseTool] = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)


    async def agent_node(state: MessagesState) -> dict:
        messages = list(state["messages"])

        # Prepend system prompt on the very first call (before any tool rounds)
        if system_prompt and not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=system_prompt)] + messages

        response: AIMessage = await llm_with_tools.ainvoke(messages)
        log.debug(
            "react_agent.llm_response",
            tool_calls=len(getattr(response, "tool_calls", []) or []),
        )
        return {"messages": [response]}


    async def _run_one(tc: dict) -> ToolMessage:
        name: str = tc["name"]
        args: dict = tc.get("args", {})
        call_id: str = tc["id"]

        if name not in tool_map:
            log.warning("react_agent.unknown_tool", tool=name)
            return ToolMessage(
                tool_call_id=call_id,
                content=json.dumps({"error": f"Unknown tool '{name}'"}),
            )

        try:
            raw_result = await tool_map[name].ainvoke(args)
            result_text = (
                raw_result if isinstance(raw_result, str) else json.dumps(raw_result)
            )
            try:
                check_for_injection(result_text, source=f"tool:{name}")
            except InjectionDetected as inj:
                # A compromised tool output must abort the entire agent run.
                # Silently continuing would let the injected payload reach the LLM.
                log.error(
                    "react_agent.injection_in_tool_output",
                    tool=name,
                    pattern=inj.pattern_label,
                )
                raise  # propagates to domain_agents.py exception handler
            log.info("react_agent.tool_executed", tool=name)
        except Exception as exc:
            result_text = json.dumps({"error": f"Tool '{name}' raised: {str(exc)[:200]}"})
            log.error("react_agent.tool_error", tool=name, error=str(exc))

        return ToolMessage(tool_call_id=call_id, content=result_text)

    async def tools_node(state: MessagesState) -> dict:
        last: AIMessage = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", []) or []
        if not tool_calls:
            return {"messages": []}
        tool_messages = await asyncio.gather(*(_run_one(tc) for tc in tool_calls))
        return {"messages": list(tool_messages)}


    def _route(state: MessagesState) -> str:
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", None) or []

        # Count how many tool-call rounds have happened so far
        rounds = sum(
            1
            for m in state["messages"]
            if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
        )

        if tool_calls and rounds < max_iterations:
            return "tools"
        return END


    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()
