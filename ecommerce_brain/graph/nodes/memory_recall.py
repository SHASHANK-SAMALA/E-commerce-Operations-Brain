"""Memory recall node — KEDB pgvector search + Mem0 semantic recall.

Defined as async and wraps the synchronous SQLAlchemy kedb.recall() call in
a thread-pool executor so the async LangGraph event loop is never blocked.
"""

from __future__ import annotations

import asyncio

import structlog
from opentelemetry import trace

from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.memory import kedb
from ecommerce_brain.memory.mem0_integration import recall_similar

log = structlog.get_logger(__name__)
_tracer = trace.get_tracer("ecommerce_brain.memory_recall")


def _normalize_text(value: str) -> str:
    """Normalize text for stable dedup checks across memory sources."""
    return " ".join(value.strip().lower().split())


async def memory_recall_node(state: GraphState) -> dict:
    with _tracer.start_as_current_span("memory_recall_node") as span:
        query = state["query"]
        span.set_attribute("query_id", state.get("query_id", ""))
        try:
            # Run synchronous SQLAlchemy calls in a thread pool so the async
            # LangGraph event loop is never blocked during DB I/O.
            loop = asyncio.get_event_loop()
            context = await loop.run_in_executor(None, kedb.recall, query, 3)

            # Layer 3: Mem0 semantic recall for natural language memory
            mem0_results = recall_similar(query, session_id=state.get("session_id"), limit=3)
            if mem0_results:
                seen_text: set[str] = {
                    _normalize_text(text)
                    for text in context.recommended_actions_from_history
                    if isinstance(text, str) and text.strip()
                }
                for entry in context.kedb_entries:
                    symptom = entry.get("symptom_summary", "")
                    if isinstance(symptom, str) and symptom.strip():
                        seen_text.add(_normalize_text(symptom))

                    root_cause = entry.get("root_cause", "")
                    if isinstance(root_cause, str) and root_cause.strip():
                        seen_text.add(_normalize_text(root_cause))

                    for step in entry.get("resolution_steps", []):
                        if isinstance(step, str) and step.strip():
                            seen_text.add(_normalize_text(step))

                for mem in mem0_results:
                    memory_text = mem.get("memory", "")
                    normalized = (
                        _normalize_text(memory_text) if isinstance(memory_text, str) else ""
                    )
                    if normalized and normalized not in seen_text:
                        context.recommended_actions_from_history.append(memory_text)
                        seen_text.add(normalized)
                if not context.historical_pattern_found and mem0_results:
                    context.historical_pattern_found = True

            span.set_attribute("kedb_hits", len(context.kedb_entries))
            span.set_attribute("mem0_hits", len(mem0_results))
            span.set_attribute("pattern_found", context.historical_pattern_found)

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
            span.record_exception(exc)
            span.set_attribute("error", True)
            return {
                "memory_context": None,
                "audit_log": [
                    {"node": "memory_recall", "event": "failed", "error": str(exc)[:200]}
                ],
            }
