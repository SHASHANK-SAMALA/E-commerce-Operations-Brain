"""HITL node — pauses graph execution via LangGraph interrupt().

Graph state is persisted to PostgreSQL via PostgresSaver.
Resume via POST /api/v1/investigate/{id}/resume after human decision.
"""

from __future__ import annotations

import json

import structlog
from langgraph.types import interrupt

from ecommerce_brain.graph.state import GraphState

log = structlog.get_logger(__name__)


def hitl_node(state: GraphState) -> dict:
    proposed = state.get("proposed_actions", [])

    if not proposed:
        # Nothing to approve — skip HITL
        log.info("hitl.skipped", reason="no_proposed_actions")
        return {
            "hitl_status": "approved",
            "approved_actions": [],
            "audit_log": [{"node": "hitl", "event": "skipped", "reason": "no_proposed_actions"}],
        }

    # ALWAYS pause for human approval when there are proposed actions.
    # Checking the intent label is WRONG — a "diagnose" query can still surface
    # actionable remedies that write to the database and need sign-off.
    # The only safe guard is: if proposed_actions is non-empty → interrupt.

    # Run dry_run for each proposed action before presenting to user
    dry_run_results: dict[str, str] = {}
    for action in proposed:
        from ecommerce_brain.tools.registry import registry

        tool_name = action["action_type"]
        tool = registry.get(tool_name)
        if tool:
            try:
                params_with_dry_run = {**action.get("params", {}), "dry_run": True}
                result = tool.invoke(params_with_dry_run)
                dry_run_results[action["action_id"]] = json.dumps(result)
            except Exception as exc:
                dry_run_results[action["action_id"]] = f"dry_run_error: {exc!s}"

    # Attach dry_run results to proposed actions
    updated_proposed = []
    for action in proposed:
        updated = dict(action)
        updated["dry_run_result"] = dry_run_results.get(action["action_id"])
        updated_proposed.append(updated)

    log.info("hitl.pausing", actions=len(proposed), intent=state.get("intent"))

    # LangGraph interrupt — suspends execution, saves state to Postgres.
    # Resume signal: {"approved": True, "approved_action_ids": [...]} or {"approved": False}
    decision = interrupt(
        {
            "type": "hitl_approval_required",
            "query_id": state["query_id"],
            "proposed_actions": updated_proposed,
            "root_cause_summary": (
                state.get("root_cause_report", {}).get("summary", "")
                if isinstance(state.get("root_cause_report"), dict)
                else (
                    state.get("root_cause_report").summary
                    if state.get("root_cause_report")
                    else ""
                )
            ),
        }
    )

    # Execution resumes here after human decision
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

    # Filter to approved action IDs (or all if not specified)
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

