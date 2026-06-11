"""Memory writer node — persists completed investigation to KEDB incident store + Mem0."""

from __future__ import annotations

import time

import structlog

from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.memory.kedb import save_incident, save_or_update_kedb_entry
from ecommerce_brain.memory.mem0_integration import add_investigation_memory

log = structlog.get_logger(__name__)


def memory_writer_node(state: GraphState) -> dict:
    report = state.get("root_cause_report")
    if not report:
        return {"audit_log": [{"node": "memory_writer", "event": "skipped", "reason": "no_report"}]}

    start_ms = state.get("investigation_start_ms", int(time.time() * 1000))
    duration_ms = int(time.time() * 1000) - start_ms
    root_causes = [rc.cause for rc in report.root_causes] if hasattr(report, "root_causes") else []
    actions_proposed = (
        [a.model_dump() for a in report.proposed_actions]
        if hasattr(report, "proposed_actions")
        else []
    )
    actions_approved = [
        {"action_id": a["action_id"], "action_type": a["action_type"]}
        for a in state.get("approved_actions", [])
    ]
    actions_executed = state.get("execution_results", [])

    try:
        incident_id = save_incident(
            query=state["query"],
            intent=state.get("intent", "diagnose"),
            domains=state.get("domains_required", []),
            root_causes=root_causes,
            evidence_score=(
                report.evidence_score if hasattr(report, "evidence_score") else 0.0
            ),
            actions_proposed=actions_proposed,
            actions_approved=actions_approved,
            actions_executed=actions_executed,
            tokens_used=state.get("total_tokens", 0),
            duration_ms=duration_ms,
        )
        log.info("memory_writer.saved", incident_id=incident_id)

        # KEDB: upsert a reusable knowledge entry from this investigation's findings.
        # Resolution steps are derived from proposed actions (action_type + impact).
        kedb_resolution_steps = [
            f"{a.get('action_type', 'unknown')}: {a.get('estimated_impact', '')}"
            for a in actions_proposed
            if isinstance(a, dict) and a.get("action_type")
        ]
        save_or_update_kedb_entry(
            query=state["query"],
            root_causes=root_causes,
            resolution_steps=kedb_resolution_steps,
            affected_domains=state.get("domains_required", []),
        )

        # Mem0: store semantic memory of this investigation
        actions_taken = [
            f"{a.get('action_type', 'unknown')}"
            for a in actions_executed
            if isinstance(a, dict) and a.get("success", False)
        ]
        add_investigation_memory(
            query_id=state["query_id"],
            query=state["query"],
            root_causes=root_causes,
            actions_taken=actions_taken,
            evidence_score=(
                report.evidence_score if hasattr(report, "evidence_score") else 0.0
            ),
            session_id=state.get("session_id"),
        )

        return {"audit_log": [{"node": "memory_writer", "event": "saved", "incident_id": incident_id}]}  # noqa: E501
    except Exception as exc:
        log.error("memory_writer.failed", error=str(exc))
        return {"audit_log": [{"node": "memory_writer", "event": "failed", "error": str(exc)[:200]}]}  # noqa: E501
