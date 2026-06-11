"""Domain agent nodes — sales, inventory, marketing, support.

Each node:
1. Calls its whitelisted tools (via asyncio.gather for Level-2 parallelism)
2. Passes tool results + memory context to LLM
3. Returns a typed domain report (Pydantic model)
"""

from __future__ import annotations

import json

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
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
from ecommerce_brain.tools.mcp_loader import execute_mcp_tools_for_agent

log = structlog.get_logger(__name__)
_tracer = trace.get_tracer("ecommerce_brain.domain_agents")


async def _call_domain_agent(domain: str, state: GraphState, schema_class) -> dict:
    with _tracer.start_as_current_span(f"{domain}_agent") as span:
        span.set_attribute("query_id", state.get("query_id", ""))
        span.set_attribute("intent", state.get("intent", ""))
        span.set_attribute("domain", domain)
        spec = get_agent(f"{domain}_agent")

        llm = agent_llm(temperature=spec.temperature)

        # Execute tools exclusively via MCP server — no local fallback
        try:
            raw_results = await execute_mcp_tools_for_agent(domain)
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

        # Guardrail: sanitize each tool output before sending to LLM
        tool_results = {}
        for tool_name, result in raw_results.items():
            tool_text = json.dumps(result)
            try:
                check_for_injection(tool_text, source=f"tool:{tool_name}")
                tool_results[tool_name] = result
            except Exception:
                tool_results[tool_name] = {"warning": "tool output sanitized — potential injection detected"}

        memory = state.get("memory_context")
        memory_hint = ""
        if memory and getattr(memory, "kedb_entries", None):
            first = memory.kedb_entries[0]
            memory_hint = (
                f"\nHistorical context: {first.get('symptom_summary', '')}"
                f" → {first.get('root_cause', '')[:200]}"
            )

        messages = [
            SystemMessage(content=spec.system_prompt + memory_hint),
            HumanMessage(
                content=(
                    f"Query: {state['query']}\n\nTool results:\n"  # noqa: E501
                    f"{json.dumps(tool_results, indent=2)}\n\n"
                    f"Return a {schema_class.__name__} JSON object."
                ),
            ),
        ]

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
