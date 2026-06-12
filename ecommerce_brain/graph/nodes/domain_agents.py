"""Domain agent nodes — sales, inventory, marketing, support.

Agentic pattern: each domain node spins up a dedicated ``create_react_agent``
(ReAct = Reason + Act) backed by its own MCP server.

Flow per domain:
  1. Load MCP tool definitions (no execution yet).
  2. Build a ReAct agent: StateGraph(agent_node → tools_node → agent_node …).
  3. Invoke the agent with the user query; it autonomously decides which tools
     to call and how many times (up to _MAX_ITERATIONS rounds).
  4. Extract the final AIMessage from the conversation and ask the LLM to
     produce a strongly-typed domain report (SalesReport, InventoryReport, …).

The four domain agents (sales, inventory, marketing, support) run in parallel
via LangGraph's Send fan-out — each is an independent ReAct agent with its
own LLM instance and its own MCP tool set.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from opentelemetry import trace

from ecommerce_brain.agents.react_agent import create_react_agent
from ecommerce_brain.agents.registry import get_agent
from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.llm import agent_llm
from ecommerce_brain.schemas.outputs import (
    InventoryReport,
    MarketingReport,
    SalesReport,
    SupportReport,
)
from ecommerce_brain.tools.mcp_loader import get_mcp_tools

log = structlog.get_logger(__name__)
_tracer = trace.get_tracer("ecommerce_brain.domain_agents")

# Hard cap passed into each ReAct agent — prevents runaway tool-call loops.
_MAX_ITERATIONS = 5


async def _call_domain_agent(domain: str, state: GraphState, schema_class) -> dict:
    with _tracer.start_as_current_span(f"{domain}_agent") as span:
        span.set_attribute("query_id", state.get("query_id", ""))
        span.set_attribute("intent", state.get("intent", ""))
        span.set_attribute("domain", domain)

        spec = get_agent(f"{domain}_agent")
        llm = agent_llm(temperature=spec.temperature)

        # ── Step 1: fetch MCP tool definitions (no execution yet) ─────────────
        try:
            tools = await get_mcp_tools(domain)
        except Exception as exc:
            log.error(f"mcp_tools.unavailable_{domain}", error=str(exc))
            span.set_attribute("success", False)
            span.record_exception(exc)
            return {
                "success": False,
                "error": (
                    f"MCP server for '{domain}' is unreachable. "
                    f"Start it with: python start_mcp_servers.py\nDetail: {str(exc)[:200]}"
                ),
            }

        # Enforce the YAML whitelist: only expose tools the agent is allowed to call.
        if spec.whitelisted_tools:
            tools = [t for t in tools if t.name in spec.whitelisted_tools]

        span.set_attribute("tools_available", [t.name for t in tools])

        # ── Step 2: build a dedicated ReAct agent for this domain ─────────────
        # Each domain gets its own agent instance with its own system prompt
        # and its own MCP tool set — fully isolated from other domain agents.
        memory = state.get("memory_context")
        memory_hint = ""
        if memory and getattr(memory, "kedb_entries", None):
            first = memory.kedb_entries[0]
            memory_hint = (
                f"\nHistorical context: {first.get('symptom_summary', '')}"
                f" → {first.get('root_cause', '')[:200]}"
            )

        agent = create_react_agent(
            llm,
            tools=tools,
            system_prompt=spec.system_prompt + memory_hint,
            max_iterations=_MAX_ITERATIONS,
        )

        # ── Step 3: run the ReAct loop ─────────────────────────────────────────
        # The agent autonomously decides which tools to call, executes them via
        # MCP, and iterates until it has enough information to answer the query.
        query_message = HumanMessage(
            content=f"Query: {state['query']}\n\nAnalyse using the available tools."
        )
        try:
            agent_output = await agent.ainvoke({"messages": [query_message]})
        except Exception as exc:
            log.error(f"{domain}_agent.react_loop_failed", error=str(exc))
            span.set_attribute("success", False)
            span.record_exception(exc)
            return {"success": False, "error": str(exc)}

        # Count how many tool calls were made across all iterations
        total_tool_calls = sum(
            len(getattr(m, "tool_calls", []) or [])
            for m in agent_output["messages"]
            if isinstance(m, AIMessage)
        )
        span.set_attribute("total_tool_calls", total_tool_calls)
        log.info(
            f"{domain}_agent.react_done",
            total_messages=len(agent_output["messages"]),
            total_tool_calls=total_tool_calls,
        )

        # ── Step 4: extract structured domain report ───────────────────────────
        # Re-invoke the LLM with the full conversation and ask for structured JSON.
        # Using with_structured_output ensures the report matches the Pydantic schema.
        messages = agent_output["messages"] + [
            HumanMessage(
                content=(
                    f"Based on the tool results above, return a {schema_class.__name__} "
                    "JSON object. Do not add any prose — only the JSON."
                )
            )
        ]
        structured_llm = llm.with_structured_output(schema_class, method="function_calling")
        try:
            report = await structured_llm.ainvoke(messages)
            span.set_attribute("success", True)
            return {"success": True, "report": report}
        except Exception as exc:
            log.error(f"{domain}_agent.structured_output_failed", error=str(exc))
            span.set_attribute("success", False)
            span.record_exception(exc)
            return {"success": False, "error": str(exc)}


async def sales_agent_node(state: GraphState) -> dict:
    result = await _call_domain_agent("sales", state, SalesReport)
    if result["success"]:
        return {
            "sales_report": result["report"],
            "audit_log": [{"node": "sales_agent", "event": "completed"}],
        }
    return {
        "sales_report": None,
        "audit_log": [{"node": "sales_agent", "event": "failed", "error": result["error"]}],
    }


async def inventory_agent_node(state: GraphState) -> dict:
    result = await _call_domain_agent("inventory", state, InventoryReport)
    if result["success"]:
        return {
            "inventory_report": result["report"],
            "audit_log": [{"node": "inventory_agent", "event": "completed"}],
        }
    return {
        "inventory_report": None,
        "audit_log": [{"node": "inventory_agent", "event": "failed", "error": result["error"]}],
    }


async def marketing_agent_node(state: GraphState) -> dict:
    result = await _call_domain_agent("marketing", state, MarketingReport)
    if result["success"]:
        return {
            "marketing_report": result["report"],
            "audit_log": [{"node": "marketing_agent", "event": "completed"}],
        }
    return {
        "marketing_report": None,
        "audit_log": [{"node": "marketing_agent", "event": "failed", "error": result["error"]}],
    }


async def support_agent_node(state: GraphState) -> dict:
    result = await _call_domain_agent("support", state, SupportReport)
    if result["success"]:
        return {
            "support_report": result["report"],
            "audit_log": [{"node": "support_agent", "event": "completed"}],
        }
    return {
        "support_report": None,
        "audit_log": [{"node": "support_agent", "event": "failed", "error": result["error"]}],
    }
