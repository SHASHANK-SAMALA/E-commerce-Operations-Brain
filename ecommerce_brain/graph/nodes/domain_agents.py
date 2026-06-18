"""Domain agent nodes â€” sales, inventory, marketing, support.

Agentic pattern: each domain node spins up a dedicated ``create_react_agent``
(ReAct = Reason + Act) backed by its own MCP server.

Flow per domain:
  1. Load MCP tool definitions (no execution yet).
  2. Build a ReAct agent: StateGraph(agent_node â†’ tools_node â†’ agent_node â€¦).
  3. Invoke the agent with the user query; it autonomously decides which tools
     to call and how many times (up to MAX_ITERATIONS rounds).
  4. Extract the final AIMessage from the conversation and ask the LLM to
     produce a strongly-typed domain report (SalesReport, InventoryReport, â€¦).

The four domain agents (sales, inventory, marketing, support) run in parallel
via LangGraph's Send fan-out â€” each is an independent ReAct agent with its
own LLM instance and its own MCP tool set.
"""

from __future__ import annotations

import time

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from opentelemetry import trace

from ecommerce_brain.agents.react_agent import MAX_ITERATIONS, create_react_agent
from ecommerce_brain.agents.registry import get_agent
from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.llm import agent_llm
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

    # Filter KEDB entries relevant to this domain.
    # An entry with no affected_domains is shown to all agents (general pattern).
    domain_kedb = [
        entry for entry in (memory.kedb_entries or [])
        if not entry.get("affected_domains") or domain in entry.get("affected_domains", [])
    ]

    for entry in domain_kedb[:2]:
        symptom = entry.get("symptom_summary", "")
        cause   = entry.get("root_cause", "")
        steps   = entry.get("resolution_steps", [])
        count   = entry.get("occurrence_count", 1)
        if not (symptom or cause):
            continue
        part = f"Pattern ({count}x): {symptom}" if symptom else f"Root cause: {cause}"
        if cause and symptom:
            part += f"\n  â†’ Cause: {cause[:300]}"
        if steps:
            part += f"\n  Previously effective: {'; '.join(str(s) for s in steps[:3])}"
        hints.append(part)

    if not hints and memory.recommended_actions_from_history:
        hints.append(
            "Historical recommendations: "
            + "; ".join(memory.recommended_actions_from_history[:3])
        )

    if not hints:
        return ""

    return (
        "\n\n=== HISTORICAL CONTEXT (for pattern recognition ONLY â€” "
        "do NOT use as action parameters) ===\n"
        + "\n\n".join(hints)
        + "\n=== END HISTORICAL CONTEXT ==="
    )


async def _call_domain_agent(domain: str, state: GraphState, schema_class) -> dict:
    agent_start_ms = int(time.time() * 1000)
    with _tracer.start_as_current_span(f"{domain}_agent") as span:
        span.set_attribute("query_id", state.get("query_id", ""))
        span.set_attribute("intent", state.get("intent", ""))
        span.set_attribute("domain", domain)

        # â”€â”€ Prometheus per-agent counter â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        try:
            from ecommerce_brain.observability.setup import agent_call_counter
            agent_call_counter.add(1, {"domain": domain})
        except Exception:
            pass

        spec = get_agent(f"{domain}_agent")
        llm = agent_llm(temperature=spec.temperature)

        # â”€â”€ Step 1: fetch MCP tool definitions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        try:
            tools = await get_mcp_tools(domain)
        except Exception as exc:
            log.error(f"mcp_tools.unavailable_{domain}", error=str(exc))
            span.set_attribute("success", False)
            span.record_exception(exc)
            return {"success": False, "error": str(exc)[:300]}

        # Enforce YAML whitelist: only expose tools the agent is allowed to call.
        if spec.whitelisted_tools:
            tools = [t for t in tools if t.name in spec.whitelisted_tools]

        span.set_attribute("tools_available", [t.name for t in tools])

        # â”€â”€ Step 2: build domain-scoped memory hint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        memory = state.get("memory_context")
        memory_hint = _get_domain_memory_hint(domain, memory)

        # â”€â”€ Step 3: build the ReAct agent â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        agent = create_react_agent(
            llm,
            tools=tools,
            system_prompt=spec.system_prompt + memory_hint,
            max_iterations=MAX_ITERATIONS,
        )

        # â”€â”€ Step 4: run the ReAct loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        query_message = HumanMessage(
            content=f"Query: {state['query']}\n\nAnalyse using the available tools."
        )

        llm_start_ms = int(time.time() * 1000)
        try:
            agent_output = await agent.ainvoke({"messages": [query_message]})
        except Exception as exc:
            log.error(f"{domain}_agent.react_loop_failed", error=str(exc))
            span.set_attribute("success", False)
            span.record_exception(exc)
            return {"success": False, "error": str(exc)}
        finally:
            llm_elapsed_ms = int(time.time() * 1000) - llm_start_ms
            try:
                from ecommerce_brain.observability.setup import (
                    agent_latency_histogram,
                    llm_latency_histogram,
                )
                llm_latency_histogram.record(llm_elapsed_ms, {"domain": domain})
                agent_latency_histogram.record(
                    int(time.time() * 1000) - agent_start_ms, {"domain": domain}
                )
            except Exception:
                pass

        # ── Step 5: extract structured domain report â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        messages = agent_output["messages"] + [
            HumanMessage(
                content=(
                    f"Based on the tool results above, return a {schema_class.__name__} "
                    "JSON object. Do not add any prose â€” only the JSON."
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
        "error": result.get("error"),
        "audit_log": [{"node": "sales_agent", "event": "failed", "error": result.get("error", "")[:200]}],
    }


async def inventory_agent_node(state: GraphState) -> dict:
    result = await _call_domain_agent("inventory", state, InventoryReport)
    if result["success"]:
        return {
            "inventory_report": result["report"],
            "audit_log": [{"node": "inventory_agent", "event": "completed"}],
        }
    return {
        "error": result.get("error"),
        "audit_log": [{"node": "inventory_agent", "event": "failed", "error": result.get("error", "")[:200]}],
    }


async def marketing_agent_node(state: GraphState) -> dict:
    result = await _call_domain_agent("marketing", state, MarketingReport)
    if result["success"]:
        return {
            "marketing_report": result["report"],
            "audit_log": [{"node": "marketing_agent", "event": "completed"}],
        }
    return {
        "error": result.get("error"),
        "audit_log": [{"node": "marketing_agent", "event": "failed", "error": result.get("error", "")[:200]}],
    }


async def support_agent_node(state: GraphState) -> dict:
    result = await _call_domain_agent("support", state, SupportReport)
    if result["success"]:
        return {
            "support_report": result["report"],
            "audit_log": [{"node": "support_agent", "event": "completed"}],
        }
    return {
        "error": result.get("error"),
        "audit_log": [{"node": "support_agent", "event": "failed", "error": result.get("error", "")[:200]}],
    }
