"""Domain agent nodes — sales, inventory, marketing, support.

Agentic pattern: each domain node spins up a dedicated ``create_react_agent``
(ReAct = Reason + Act) backed by its own MCP server.

Flow per domain:
  1. Load MCP tool definitions (no execution yet).
  2. Build a ReAct agent: StateGraph(agent_node → tools_node → agent_node …).
  3. Invoke the agent with the user query; it autonomously decides which tools
     to call and how many times (up to MAX_ITERATIONS rounds).
  4. Extract the final AIMessage from the conversation and ask the LLM to
     produce a strongly-typed domain report (SalesReport, InventoryReport, …).

The four domain agents (sales, inventory, marketing, support) run in parallel
via LangGraph's Send fan-out — each is an independent ReAct agent with its
own LLM instance and its own MCP tool set.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from langchain_core.messages import HumanMessage
from opentelemetry import trace

from ecommerce_brain.agents.react_agent import MAX_ITERATIONS, create_react_agent
from ecommerce_brain.utils.time import now_ms
from ecommerce_brain.agents.registry import get_agent
from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.llm import agent_llm
from ecommerce_brain.observability.safe_metrics import safe_add, safe_record
from ecommerce_brain.observability.setup import (
    agent_call_counter,
    agent_latency_histogram,
    llm_latency_histogram,
)
from ecommerce_brain.schemas.memory import MemoryContext
from ecommerce_brain.schemas.outputs import (
    InventoryReport,
    MarketingReport,
    SalesReport,
    SupportReport,
)
from ecommerce_brain.tools.mcp_loader import get_mcp_tools

log = structlog.get_logger(__name__)
_tracer = trace.get_tracer("ecommerce_brain.domain_agents")


def _get_domain_memory_hint(domain: str, memory: MemoryContext | None) -> str:
    """Build a domain-scoped memory hint from the pre-fetched MemoryContext.

    Filters KEDB entries to those affecting the current domain and includes
    the full resolution_steps list (not just 200 chars of root cause text).
    """
    if not memory:
        return ""

    hints: list[str] = []

    domain_kedb = [
        entry for entry in (memory.kedb_entries or [])
        if not entry.get("affected_domains") or domain in entry.get("affected_domains", [])
    ]

    for entry in domain_kedb[:2]:
        symptom = entry.get("symptom_summary", "")
        cause = entry.get("root_cause", "")
        steps = entry.get("resolution_steps", [])
        count = entry.get("occurrence_count", 1)
        if not (symptom or cause):
            continue
        part = f"Pattern ({count}x): {symptom}" if symptom else f"Root cause: {cause}"
        if cause and symptom:
            part += f"\n  → Cause: {cause[:300]}"
        if steps:
            part += f"\n  Previously effective: {'; '.join(str(s) for s in steps[:3])}"
        hints.append(part)

    domain_specific_mems = (memory.domain_memories or {}).get(domain, [])
    fallback_mems = domain_specific_mems or memory.recommended_actions_from_history
    if not hints and fallback_mems:
        hints.append("Historical recommendations: " + "; ".join(fallback_mems[:3]))

    if not hints:
        return ""

    return (
        "\n\n=== HISTORICAL CONTEXT (for pattern recognition ONLY — "
        "do NOT use as action parameters) ===\n"
        + "\n\n".join(hints)
        + "\n=== END HISTORICAL CONTEXT ==="
    )


async def _call_domain_agent(domain: str, state: GraphState, schema_class: type) -> dict:
    """Run a full ReAct loop for the given domain and return a typed report.

    Args:
        domain: Domain name ("sales", "inventory", "marketing", "support").
        state: Current graph state passed in via LangGraph Send fan-out.
        schema_class: Pydantic model class for structured LLM output.

    Returns:
        Dict with "success": True and "report" on success, or
        "success": False and "error" on failure.
    """
    agent_start_ms = now_ms()
    with _tracer.start_as_current_span(f"{domain}_agent") as span:
        span.set_attribute("query_id", state.get("query_id", ""))
        span.set_attribute("intent", state.get("intent", ""))
        span.set_attribute("domain", domain)

        safe_add(agent_call_counter, 1, {"domain": domain})

        spec = get_agent(f"{domain}_agent")
        llm = agent_llm(temperature=spec.temperature)

        try:
            tools = await get_mcp_tools(domain)
        except Exception as exc:
            log.error("mcp_tools.unavailable", domain=domain, error=str(exc))
            span.set_attribute("success", False)
            span.record_exception(exc)
            return {"success": False, "error": str(exc)[:300]}

        if spec.whitelisted_tools:
            tools = [t for t in tools if t.name in spec.whitelisted_tools]

        span.set_attribute("tools_available", [t.name for t in tools])

        memory = state.get("memory_context")
        memory_hint = _get_domain_memory_hint(domain, memory)

        agent = create_react_agent(
            llm,
            tools=tools,
            system_prompt=spec.system_prompt + memory_hint,
            max_iterations=MAX_ITERATIONS,
        )

        query_message = HumanMessage(
            content=f"Query: {state['query']}\n\nAnalyse using the available tools."
        )

        llm_start_ms = now_ms()
        try:
            agent_output = await agent.ainvoke({"messages": [query_message]})
        except Exception as exc:
            log.error("domain_agent.react_loop_failed", domain=domain, error=str(exc))
            span.set_attribute("success", False)
            span.record_exception(exc)
            return {"success": False, "error": str(exc)}
        finally:
            llm_elapsed_ms = now_ms() - llm_start_ms
            safe_record(llm_latency_histogram, llm_elapsed_ms, {"domain": domain})
            safe_record(
                agent_latency_histogram,
                now_ms() - agent_start_ms,
                {"domain": domain},
            )

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
            log.error("domain_agent.structured_output_failed", domain=domain, error=str(exc))
            span.set_attribute("success", False)
            span.record_exception(exc)
            return {"success": False, "error": str(exc)}


def _make_domain_node(domain: str, schema_class: type) -> Callable[[GraphState], Any]:
    """Factory that produces a typed domain agent node function.

    Eliminates the four structurally identical wrapper functions.  The
    returned coroutine carries a human-readable __name__ so LangGraph can
    display it correctly in traces.
    """
    async def node(state: GraphState) -> dict:
        result = await _call_domain_agent(domain, state, schema_class)
        report_key = f"{domain}_report"
        node_name = f"{domain}_agent"
        if result["success"]:
            return {
                report_key: result["report"],
                "audit_log": [{"node": node_name, "event": "completed"}],
            }
        return {
            "error": result.get("error"),
            "audit_log": [
                {
                    "node": node_name,
                    "event": "failed",
                    "error": (result.get("error") or "")[:200],
                }
            ],
        }

    node.__name__ = f"{domain}_agent_node"
    node.__qualname__ = f"{domain}_agent_node"
    return node


sales_agent_node = _make_domain_node("sales", SalesReport)
inventory_agent_node = _make_domain_node("inventory", InventoryReport)
marketing_agent_node = _make_domain_node("marketing", MarketingReport)
support_agent_node = _make_domain_node("support", SupportReport)
