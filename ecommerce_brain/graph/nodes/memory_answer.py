"""Memory answer node — handles memory_query intent without calling domain agents.

When a user asks "What did we do last time sales dropped?" the coordinator sets
intent="memory_query" with domains_required=[]. This node intercepts the path
after memory_recall and constructs a RootCauseReport directly from the
MemoryContext (KEDB + Mem0 results), bypassing domain agents, reflection,
synthesis LLM call, and HITL — none of which make sense for a memory lookup.
"""

from __future__ import annotations

import structlog

from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.utils.time import now_ms
from ecommerce_brain.schemas.outputs import RootCause, RootCauseReport

log = structlog.get_logger(__name__)


def memory_answer_node(state: GraphState) -> dict:
    """Build a RootCauseReport from historical memory without any LLM call."""
    memory = state.get("memory_context")
    query = state["query"]
    start_ms = state.get("investigation_start_ms", now_ms())
    duration_ms = now_ms() - start_ms

    root_causes: list[RootCause] = []
    summary_parts: list[str] = []
    similar_incident_ids: list[str] = []

    if memory:
        # ── KEDB entries ───────────────────────────────────────────────────────
        for entry in memory.kedb_entries[:3]:
            symptom = entry.get("symptom_summary", "")
            cause = entry.get("root_cause", "")
            domains = entry.get("affected_domains", ["unknown"])
            steps = entry.get("resolution_steps", [])
            count = entry.get("occurrence_count", 1)

            if cause:
                root_causes.append(
                    RootCause(
                        cause=cause[:300],
                        domain=", ".join(domains) if domains else "unknown",
                        evidence=(
                            f"Seen {count} time(s). Symptom: {symptom[:150]}"
                            if symptom
                            else f"Seen {count} time(s)"
                        ),
                        confidence="MEDIUM",
                    )
                )
            part = f"• Pattern: {symptom}" if symptom else f"• Root cause: {cause}"
            if steps:
                part += f"\n  Previously effective: {'; '.join(str(s) for s in steps[:3])}"
            if part.strip():
                summary_parts.append(part)

        # ── Similar past incidents ─────────────────────────────────────────────
        for inc in memory.similar_incidents[:2]:
            similar_incident_ids.append(inc.id)
            for rc in inc.root_causes[:1]:
                summary_parts.append(f"• Past incident ({inc.created_at[:10]}): {rc}")

    if not summary_parts:
        summary = (
            f"No historical records found matching: '{query}'. "
            "This appears to be a novel incident with no prior pattern in the KEDB or incident store."
        )
        root_causes = [
            RootCause(
                cause="No historical pattern found",
                domain="memory",
                evidence="KEDB and incident store returned no matching entries",
                confidence="LOW",
            )
        ]
    else:
        intro = f"Historical analysis for: '{query}'\n\n"
        summary = intro + "\n".join(summary_parts[:5])
        if memory and memory.recommended_actions_from_history:
            recs = memory.recommended_actions_from_history[:3]
            summary += f"\n\nPreviously recommended actions: {'; '.join(recs)}"

    report = RootCauseReport(
        query_id=state["query_id"],
        query=query,
        root_causes=root_causes,
        evidence_score=0.8 if (memory and memory.historical_pattern_found) else 0.1,
        summary=summary,
        proposed_actions=[],  # memory queries never produce actions
        domains_analyzed=[],
        similar_past_incidents=similar_incident_ids,
        investigation_duration_ms=duration_ms,
        total_tokens_used=0,
    )

    log.info(
        "memory_answer.done",
        pattern_found=bool(memory and memory.historical_pattern_found),
        kedb_hits=len(memory.kedb_entries) if memory else 0,
        incident_hits=len(memory.similar_incidents) if memory else 0,
    )

    return {
        "root_cause_report": report,
        "proposed_actions": [],
        "skip_hitl": True,  # memory queries are read-only; HITL interrupt is not needed
        "hitl_status": "pending",
        "approved_actions": [],
        "execution_results": [],
        "audit_log": [
            {
                "node": "memory_answer",
                "event": "answered",
                "pattern_found": bool(memory and memory.historical_pattern_found),
                "kedb_hits": len(memory.kedb_entries) if memory else 0,
            }
        ],
    }
