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
from ecommerce_brain.schemas.memory import MemoryContext

log = structlog.get_logger(__name__)
_tracer = trace.get_tracer("ecommerce_brain.memory_recall")


def _normalize_text(value: str) -> str:
    """Normalize text for stable dedup checks across memory sources."""
    return " ".join(value.strip().lower().split())


def _deduplicate_mem0_results(
    mem0_results: list[dict],
    context: MemoryContext,
) -> list[str]:
    """Filter Mem0 results to exclude text already present in KEDB context.

    Builds a set of normalized strings from all KEDB entries and existing
    recommended actions, then returns only the Mem0 memory strings that are
    not already represented.

    Args:
        mem0_results: Raw Mem0 search results (list of dicts with 'memory' key).
        context: Existing MemoryContext populated from KEDB search.

    Returns:
        List of unique memory strings not already in the context.
    """
    seen_text: set[str] = {
        _normalize_text(text)
        for text in context.recommended_actions_from_history
        if isinstance(text, str) and text.strip()
    }
    for entry in context.kedb_entries:
        for field in ("symptom_summary", "root_cause"):
            val = entry.get(field, "")
            if isinstance(val, str) and val.strip():
                seen_text.add(_normalize_text(val))
        for step in entry.get("resolution_steps", []):
            if isinstance(step, str) and step.strip():
                seen_text.add(_normalize_text(step))

    unique: list[str] = []
    for mem in mem0_results:
        memory_text = mem.get("memory", "")
        normalized = _normalize_text(memory_text) if isinstance(memory_text, str) else ""
        if normalized and normalized not in seen_text:
            unique.append(memory_text)
            seen_text.add(normalized)
    return unique


async def memory_recall_node(state: GraphState) -> dict:
    """Recall KEDB patterns and Mem0 semantic memories for the query.

    Args:
        state: Current graph state with query and session/domain context.

    Returns:
        Dict with memory_context (MemoryContext | None) and audit_log entry.
    """
    with _tracer.start_as_current_span("memory_recall_node") as span:
        query = state["query"]
        span.set_attribute("query_id", state.get("query_id", ""))
        try:
            loop = asyncio.get_running_loop()
            context = await loop.run_in_executor(None, kedb.recall, query, 3)

            # Global Mem0 recall — feeds cross-domain recommended_actions_from_history.
            mem0_results = recall_similar(query, session_id=state.get("session_id"), limit=3)
            if mem0_results:
                new_memories = _deduplicate_mem0_results(mem0_results, context)
                context.recommended_actions_from_history.extend(new_memories)
                if not context.historical_pattern_found:
                    context.historical_pattern_found = True

            # Domain-scoped Mem0 recall — each agent only sees its own domain memories.
            domains_required = state.get("domains_required") or []
            for domain in domains_required:
                domain_mems = recall_similar(query, domain=domain, limit=3)
                context.domain_memories[domain] = [
                    m.get("memory", "") for m in domain_mems
                    if isinstance(m.get("memory"), str) and m.get("memory", "").strip()
                ]

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
