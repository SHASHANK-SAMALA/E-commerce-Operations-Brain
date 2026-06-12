"""Domain agent nodes — sales, inventory, marketing, support.

Agentic tool-use pattern (bind_tools loop):
  1. Load tool definitions from MCP server (no execution yet).
  2. LLM reads tool schemas + query and decides which tools to call.
  3. Execute only the tools the LLM requested, in parallel.
  4. Feed tool results back to the LLM as ToolMessages.
  5. LLM produces a structured domain report from the results it chose.

Max iterations guard prevents infinite tool-call loops.
"""

from __future__ import annotations

import asyncio
import json

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from opentelemetry import trace

from ecommerce_brain.agents.registry import get_agent
from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.guardrails.prompt_injection import check_for_injection
from ecommerce_brain.llm import agent_llm
from ecommerce_brain.schemas.outputs import (
    InventoryReport,
    MarketingReport,
    SalesReport,
    SupportReport,
)
from ecommerce_brain.tools.mcp_loader import execute_mcp_tool, get_mcp_tools

log = structlog.get_logger(__name__)
_tracer = trace.get_tracer("ecommerce_brain.domain_agents")

# Hard cap: LLM may ask for at most this many tool-call rounds per agent.
_MAX_TOOL_ITERATIONS = 5


async def _call_domain_agent(domain: str, state: GraphState, schema_class) -> dict:
    with _tracer.start_as_current_span(f"{domain}_agent") as span:
        span.set_attribute("query_id", state.get("query_id", ""))
        span.set_attribute("intent", state.get("intent", ""))
        span.set_attribute("domain", domain)
        spec = get_agent(f"{domain}_agent")
        llm = agent_llm(temperature=spec.temperature)

        # ── Step 1: load tool definitions from MCP (no execution yet) ─────────
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

        # Build a name→tool map for fast lookup during execution
        tool_map = {t.name: t for t in tools}

        # ── Step 2: bind tools to LLM so it can choose which ones to call ─────
        llm_with_tools = llm.bind_tools(tools)

        memory = state.get("memory_context")
        memory_hint = ""
        if memory and getattr(memory, "kedb_entries", None):
            first = memory.kedb_entries[0]
            memory_hint = (
                f"\nHistorical context: {first.get('symptom_summary', '')}"
                f" → {first.get('root_cause', '')[:200]}"
            )

        messages: list = [
            SystemMessage(content=spec.system_prompt + memory_hint),
            HumanMessage(content=f"Query: {state['query']}\n\nAnalyse using the available tools."),
        ]

        total_tool_calls = 0

        # ── Step 3-4: agentic loop — LLM decides tools, we execute, repeat ────
        for iteration in range(_MAX_TOOL_ITERATIONS):
            ai_response: AIMessage = await llm_with_tools.ainvoke(messages)
            messages.append(ai_response)

            # No tool calls requested — LLM is done reasoning
            if not getattr(ai_response, "tool_calls", None):
                break

            span.set_attribute(f"iteration_{iteration}_tool_calls", len(ai_response.tool_calls))
            total_tool_calls += len(ai_response.tool_calls)

            # Validate tool names before execution (LLM sometimes hallucinates names)
            valid_calls = [
                tc for tc in ai_response.tool_calls
                if tc["name"] in tool_map
            ]
            invalid_calls = [
                tc["name"] for tc in ai_response.tool_calls
                if tc["name"] not in tool_map
            ]
            if invalid_calls:
                log.warning(f"{domain}_agent.invalid_tool_calls", tools=invalid_calls)

            # Execute all valid tool calls in parallel
            async def _run_tool_call(tc: dict) -> ToolMessage:
                tool = tool_map[tc["name"]]
                args = tc.get("args", {})
                result = await execute_mcp_tool(tool, args, domain)

                # Guardrail: sanitize tool output before feeding back to LLM
                result_text = json.dumps(result)
                try:
                    check_for_injection(result_text, source=f"tool:{tc['name']}")
                except Exception:
                    result_text = json.dumps({"warning": "tool output sanitized — potential injection detected"})

                return ToolMessage(
                    tool_call_id=tc["id"],
                    content=result_text,
                )

            tool_messages = await asyncio.gather(*(_run_tool_call(tc) for tc in valid_calls))

            # Add error messages for any invalid tool calls so the LLM knows
            for tc in ai_response.tool_calls:
                if tc["name"] not in tool_map:
                    tool_messages = list(tool_messages) + [
                        ToolMessage(
                            tool_call_id=tc["id"],
                            content=json.dumps({"error": f"Unknown tool '{tc['name']}'"}),
                        )
                    ]

            messages.extend(tool_messages)
            log.info(
                f"{domain}_agent.tool_round",
                iteration=iteration,
                tools_called=[tc["name"] for tc in valid_calls],
            )

        span.set_attribute("total_tool_calls", total_tool_calls)

        # ── Step 5: structured output from the final LLM response ─────────────
        # Add a final instruction so the LLM knows to return the structured report
        messages.append(
            HumanMessage(content=f"Based on the tool results above, return a {schema_class.__name__} JSON object.")
        )

        structured_llm = llm.with_structured_output(schema_class, method="function_calling")
        try:
            report = await structured_llm.ainvoke(messages)
            span.set_attribute("success", True)
            return {"success": True, "report": report}
        except Exception as exc:
            log.error(f"{domain}_agent.failed", error=str(exc))
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
