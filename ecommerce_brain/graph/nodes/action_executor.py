"""Action executor node — runs approved actions with dry_run=False.

Falls back to local tool registry when MCP action server is unavailable.
"""

from __future__ import annotations

import json

import structlog

from ecommerce_brain.exceptions import DatabaseError
from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.memory.kadb import record_execution

log = structlog.get_logger(__name__)


def _normalize_result(result: object) -> dict:
    """Normalize MCP / local tool result to a plain dict with 'success' and 'message'.

    Args:
        result: Raw tool return value — dict, SSE content list, or string.

    Returns:
        Normalised dict guaranteed to have at least a 'success' key.
    """
    if isinstance(result, dict):
        return result
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict) and "text" in first:
            try:
                return json.loads(first["text"])
            except (json.JSONDecodeError, ValueError):
                return {"success": True, "message": str(first.get("text", ""))}
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (json.JSONDecodeError, ValueError):
            return {"success": True, "message": result}
    return {"success": True, "message": str(result)}


def _expand_actions(raw: list[dict]) -> list[dict]:
    """Normalize LLM bulk-param mistakes into per-item action dicts.

    Handles three common LLM mistakes:
    - restock_product with a bulk ``skus`` list → one action per SKU
    - restock_product missing ``quantity`` → default 100
    - increase_campaign_budget with ``channel`` key instead of ``campaign_id``

    Args:
        raw: List of action dicts from the HITL approval step.

    Returns:
        Expanded list of action dicts, each with correct per-item parameters.
    """
    expanded = []
    for action in raw:
        atype = action["action_type"]
        params = action.get("params", {})

        if atype == "restock_product":
            skus = params.get("skus")
            if isinstance(skus, list):
                qty = params.get("quantity", 100)
                for sku in skus:
                    expanded.append({**action, "params": {"sku": sku, "quantity": qty}})
                continue
            if "quantity" not in params:
                params = {**params, "quantity": 100}
                action = {**action, "params": params}

        elif atype == "increase_campaign_budget":
            if "campaign_id" not in params:
                fallback_id = params.get("channel", params.get("id", "unknown"))
                params = {**params, "campaign_id": fallback_id}
                action = {**action, "params": params}
            if "increase_pct" not in params:
                params = {**params, "increase_pct": params.get("increase_pct", 20.0)}
                action = {**action, "params": params}

        elif atype == "apply_discount_promotion":
            cat = params.get("category")
            if isinstance(cat, list):
                disc = params.get("discount_pct", 10.0)
                for c in cat:
                    expanded.append({**action, "params": {"category": c, "discount_pct": disc}})
                continue
            if "discount_pct" not in params:
                params = {**params, "discount_pct": 10.0}
                action = {**action, "params": params}

        expanded.append(action)
    return expanded


async def action_executor_node(state: GraphState) -> dict:
    """Execute approved actions against the MCP action server or local registry.

    Args:
        state: Current graph state with approved_actions list.

    Returns:
        Dict with execution_results list and audit_log entry.
    """
    approved = state.get("approved_actions", [])

    if not approved:
        return {
            "execution_results": [],
            "audit_log": [
                {"node": "action_executor", "event": "executed", "total": 0, "succeeded": 0}
            ],
        }

    approved = _expand_actions(approved)

    results = []

    tool_map = {}
    try:
        from ecommerce_brain.tools.mcp_loader import get_mcp_tools

        tools = await get_mcp_tools("action")
        tool_map = {t.name: ("mcp", t) for t in tools}
        log.info("action_executor.mcp_connected", tools=list(tool_map.keys()))
    except Exception as exc:
        log.warning("action_executor.mcp_unavailable", error=str(exc)[:120])

    if not tool_map:
        from ecommerce_brain.tools.registry import registry
        for name, tool in registry.items():
            tool_map[name] = ("local", tool)
        log.info("action_executor.using_local_tools", tools=list(tool_map.keys()))

    for action in approved:
        action_type = action["action_type"]
        params = action.get("params", {})
        action_id = action["action_id"]

        entry = tool_map.get(action_type)
        if not entry:
            results.append({
                "action_id": action_id,
                "success": False,
                "message": f"Tool '{action_type}' not found in MCP or local registry",
            })
            continue

        source, tool = entry
        try:
            if source == "mcp":
                result = await tool.ainvoke({**params, "dry_run": False})
            else:
                result = tool.invoke({**params, "dry_run": False})
            result = _normalize_result(result)
        except Exception as exc:
            results.append({"action_id": action_id, "success": False, "message": str(exc)})
            try:
                record_execution(action_type, success=False)
            except DatabaseError:
                pass
            log.error("action_executor.failed", action_type=action_type, error=str(exc))
        else:
            success = result.get("success", True)
            message = result.get("message", str(result))
            results.append({
                "action_id": action_id,
                "action_type": action_type,
                "success": success,
                "message": message,
            })
            try:
                record_execution(action_type, success=success, revenue_impact=0.0)
            except DatabaseError as exc:
                log.warning("action_executor.kadb_write_failed", action_type=action_type, error=str(exc))
            log.info(
                "action_executor.executed",
                action_type=action_type,
                source=source,
                success=success,
            )

    return {
        "execution_results": results,
        "audit_log": [
            {
                "node": "action_executor",
                "event": "executed",
                "total": len(approved),
                "succeeded": sum(1 for r in results if r["success"]),
            }
        ],
    }
