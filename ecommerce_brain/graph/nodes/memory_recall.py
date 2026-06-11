"""Memory recall node — KEDB pgvector search + Mem0 semantic recall."""

from __future__ import annotations

import structlog

from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.memory import kedb
from ecommerce_brain.memory.mem0_integration import recall_similar

log = structlog.get_logger(__name__)


def memory_recall_node(state: GraphState) -> dict:
    query = state["query"]
    try:
        context = kedb.recall(query, top_k=3)

        # Layer 3: Mem0 semantic recall for natural language memory
        mem0_results = recall_similar(query, session_id=state.get("session_id"), limit=3)
        if mem0_results:
            for mem in mem0_results:
                memory_text = mem.get("memory", "")
                if memory_text and memory_text not in [
                    e.get("symptom_summary", "") for e in context.kedb_entries
                ]:
                    context.recommended_actions_from_history.append(memory_text)
            if not context.historical_pattern_found and mem0_results:
                context.historical_pattern_found = True

        log.info(
            "memory_recall.done",
            pattern_found=context.historical_pattern_found,
            kedb_hits=len(context.kedb_entries),
            incident_hits=len(context.similar_incidents),
            mem0_hits=len(mem0_results),
        )
        return {
            "memory_context": context,
            "audit_log": [
                {
                    "node": "memory_recall",
                    "event": "recalled",
                    "pattern_found": context.historical_pattern_found,
                    "kedb_hits": len(context.kedb_entries),
                    "mem0_hits": len(mem0_results),
                }
            ],
        }
    except Exception as exc:
        log.warning("memory_recall.failed", error=str(exc))
        return {
            "memory_context": None,
            "audit_log": [{"node": "memory_recall", "event": "failed", "error": str(exc)[:200]}],
        }
