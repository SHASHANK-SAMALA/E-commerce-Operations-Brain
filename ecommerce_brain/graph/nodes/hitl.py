"""HITL node — pauses graph execution via LangGraph interrupt().

Design note: the project spec mentions Temporal as the HITL workflow engine.
We deliberately use LangGraph's native ``interrupt()`` + ``PostgresSaver``
instead — it gives us durable suspend/resume without the operational cost of
running a separate Temporal cluster. If a long-running, multi-day approval
workflow is ever needed, swap this single node for a Temporal activity.

Graph state is persisted to PostgreSQL via PostgresSaver.
Resume via POST /api/v1/investigate/{id}/resume after human decision.
"""

from __future__ import annotations

import json

import structlog
from langgraph.types import interrupt

from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.tools.registry import registry

log = structlog.get_logger(__name__)


def hitl_node(state: GraphState) -> dict:
    """Pause graph execution for human approval of proposed actions.

    Performs a dry-run of each proposed action before presenting them to the
    operator so they can see the projected impact before approving.

    The LangGraph interrupt() call suspends execution and persists state to
    Postgres. Execution resumes when POST /investigate/{id}/resume is called
    with the operator's decision.
    """
    proposed = state.get("proposed_actions", [])

    if not proposed:
        log.info("hitl.skipped", reason="no_proposed_actions")
        return {
            "hitl_status": "approved",
            "approved_actions": [],
            "audit_log": [{"node": "hitl", "event": "skipped", "reason": "no_proposed_actions"}],
        }

    dry_run_results: dict[str, str] = {}
    for action in proposed:
        tool_name = action["action_type"]
        tool = registry.get(tool_name)
        if not tool:
            continue
        try:
            params_with_dry_run = {**action.get("params", {}), "dry_run": True}
            result = tool.invoke(params_with_dry_run)
            dry_run_results[action["action_id"]] = json.dumps(result)
        except Exception as exc:
            log.warning(
                "hitl.dry_run_failed",
                action_id=action["action_id"],
                tool=tool_name,
                error=str(exc),
            )
            dry_run_results[action["action_id"]] = f"dry_run_error: {exc!s}"

    updated_proposed = [
        {**action, "dry_run_result": dry_run_results.get(action["action_id"])}
        for action in proposed
    ]

    log.info("hitl.pausing", actions=len(proposed), intent=state.get("intent"))

    decision = interrupt(
        {
            "type": "hitl_approval_required",
            "query_id": state["query_id"],
            "proposed_actions": updated_proposed,
            "root_cause_summary": (
                state.get("root_cause_report").summary
                if state.get("root_cause_report")
                else ""
            ),
        }
    )

    approved = decision.get("approved", False)
    approved_ids = decision.get("approved_action_ids")

    if not approved:
        return {
            "hitl_status": "rejected",
            "approved_actions": [],
            "audit_log": [
                {
                    "node": "hitl",
                    "event": "rejected",
                    "reason": decision.get("rejection_reason", ""),
                }
            ],
        }

    approved_actions = (
        [a for a in updated_proposed if a["action_id"] in approved_ids]
        if approved_ids
        else updated_proposed
    )

    return {
        "hitl_status": "approved",
        "approved_actions": approved_actions,
        "audit_log": [
            {
                "node": "hitl",
                "event": "approved",
                "approved_count": len(approved_actions),
                "total_proposed": len(proposed),
            }
        ],
    }
