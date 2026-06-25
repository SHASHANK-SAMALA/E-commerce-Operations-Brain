"""Memory writer node — persists completed investigation to KEDB incident store + Mem0.

Each storage backend (incident store, KEDB, Mem0) is written in an independent
try/except block so that a failure in one does not abort the others.
Failures are recorded in the returned audit_log so callers have visibility.
"""

from __future__ import annotations

import structlog

from ecommerce_brain.exceptions import DatabaseError
from ecommerce_brain.utils.time import now_ms
from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.memory.kedb import save_incident, save_or_update_kedb_entry
from ecommerce_brain.memory.mem0_integration import add_investigation_memory

log = structlog.get_logger(__name__)


def memory_writer_node(state: GraphState) -> dict:
    """Persist the completed investigation to all memory backends.

    Writes to three independent stores in sequence.  Each is wrapped in its
    own try/except so that a failure in any single store does not prevent the
    others from being written. All failures are surfaced in the audit_log entry.

    Args:
        state: Current graph state with root_cause_report and investigation metadata.

    Returns:
        Dict with an audit_log entry that includes incident_id and any backend
        failures so the graph surface area has full visibility.
    """
    report = state.get("root_cause_report")
    if not report:
        return {"audit_log": [{"node": "memory_writer", "event": "skipped", "reason": "no_report"}]}

    start_ms = state.get("investigation_start_ms", now_ms())
    duration_ms = now_ms() - start_ms
    root_causes = [rc.cause for rc in report.root_causes]
    actions_proposed = [a.model_dump() for a in report.proposed_actions]
    actions_approved = [
        {"action_id": a["action_id"], "action_type": a["action_type"]}
        for a in state.get("approved_actions", [])
    ]
    actions_executed = state.get("execution_results", [])

    incident_id: str | None = None
    failures: list[str] = []

    # ── Incident store ────────────────────────────────────────────────────────
    try:
        incident_id = save_incident(
            query=state["query"],
            intent=state.get("intent", "diagnose"),
            domains=state.get("domains_required", []),
            root_causes=root_causes,
            evidence_score=report.evidence_score,
            actions_proposed=actions_proposed,
            actions_approved=actions_approved,
            actions_executed=actions_executed,
            tokens_used=state.get("total_tokens", 0),
            duration_ms=duration_ms,
        )
        log.info("memory_writer.incident_saved", incident_id=incident_id)
    except (DatabaseError, Exception) as exc:
        err_msg = f"incident_store: {exc!s}"
        failures.append(err_msg)
        log.error("memory_writer.incident_failed", error=str(exc))

    # ── KEDB upsert ───────────────────────────────────────────────────────────
    try:
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
    except (DatabaseError, Exception) as exc:
        err_msg = f"kedb: {exc!s}"
        failures.append(err_msg)
        log.error("memory_writer.kedb_failed", error=str(exc))

    # ── Mem0 semantic memory ──────────────────────────────────────────────────
    try:
        actions_taken = [
            a.get("action_type", "unknown")
            for a in actions_executed
            if isinstance(a, dict) and a.get("success", False)
        ]
        evidence_score = report.evidence_score

        add_investigation_memory(
            query_id=state["query_id"],
            query=state["query"],
            root_causes=root_causes,
            actions_taken=actions_taken,
            evidence_score=evidence_score,
            session_id=state.get("session_id"),
        )
        for domain in state.get("domains_required", []):
            add_investigation_memory(
                query_id=state["query_id"],
                query=state["query"],
                root_causes=root_causes,
                actions_taken=actions_taken,
                evidence_score=evidence_score,
                domain=domain,
            )
    except Exception as exc:
        err_msg = f"mem0: {exc!s}"
        failures.append(err_msg)
        log.error("memory_writer.mem0_failed", error=str(exc))

    return {
        "audit_log": [
            {
                "node": "memory_writer",
                "event": "saved",
                "incident_id": incident_id,
                "backend_failures": failures if failures else None,
            }
        ]
    }
