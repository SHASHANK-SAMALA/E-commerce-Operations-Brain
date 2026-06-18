"""Mem0 integration — semantic memory layer on top of the incident store.

Provides natural language recall for conversational queries like:
  "What did we do last time sales dropped?"
  "Has this happened before?"

Uses pgvector as the vector store backend to stay within existing infrastructure.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

_mem0_instance = None


def _get_mem0():
    global _mem0_instance
    if _mem0_instance is not None:
        return _mem0_instance

    try:
        from mem0 import Memory

        from ecommerce_brain.config.settings import get_settings

        settings = get_settings()

        config = {
            "vector_store": {
                "provider": "pgvector",
                "config": {
                    "connection_string": settings.database_url,
                    "collection_name": "mem0_memories",
                    "embedding_model_dims": 1536,
                },
            },
            "embedder": {
                # Use openai provider — avoids needing azure-identity package.
                # The EPAM proxy is OpenAI-compatible; we pass api_key + base_url.
                "provider": "openai",
                "config": {
                    "model": settings.azure_openai_embedding_model,
                    "api_key": settings.azure_openai_api_key,
                    "openai_base_url": (
                        settings.azure_openai_endpoint.rstrip("/")
                        + f"/openai/deployments/{settings.azure_openai_embedding_model}"
                    ),
                },
            },
            "llm": {
                # Same pattern for the LLM used by mem0 internally.
                "provider": "openai",
                "config": {
                    "model": settings.azure_openai_model,
                    "api_key": settings.azure_openai_api_key,
                    "openai_base_url": (
                        settings.azure_openai_endpoint.rstrip("/")
                        + f"/openai/deployments/{settings.azure_openai_model}"
                    ),
                },
            },
        }

        _mem0_instance = Memory.from_config(config)
        log.info("mem0.initialized")
        return _mem0_instance
    except ImportError as exc:
        # Log the actual error — could be a transitive dependency missing (e.g. qdrant_client)
        log.warning("mem0.not_installed", hint="pip install mem0ai", import_error=repr(exc)[:300])
        return None
    except Exception as exc:
        log.warning("mem0.init_failed", error=repr(exc)[:300])
        return None


def add_investigation_memory(
    query_id: str,
    query: str,
    root_causes: list[str],
    actions_taken: list[str],
    evidence_score: float,
    session_id: str | None = None,
    domain: str | None = None,
) -> bool:
    """Store a completed investigation as a semantic memory."""
    mem = _get_mem0()
    if mem is None:
        return False

    summary = (
        f"Investigation '{query}' found root causes: {', '.join(root_causes)}. "
        f"Actions taken: {', '.join(actions_taken) if actions_taken else 'none'}. "
        f"Evidence score: {evidence_score:.2f}."
    )

    # Scope the user_id: per-session if available, otherwise per-domain.
    # This prevents cross-domain memory contamination (e.g. stockout patterns
    # appearing in the marketing agent's memory context).
    if session_id:
        user_id = session_id
    elif domain:
        user_id = f"ecommerce-{domain}"
    else:
        user_id = "ecommerce-ops"

    metadata = {"query_id": query_id, "evidence_score": evidence_score}
    if domain:
        metadata["domain"] = domain

    try:
        mem.add(summary, user_id=user_id, metadata=metadata)
        log.info("mem0.memory_added", query_id=query_id, user_id=user_id)
        return True
    except Exception as exc:
        log.error("mem0.add_failed", error=str(exc)[:200])
        return False


def recall_similar(
    query: str,
    session_id: str | None = None,
    domain: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Retrieve semantically similar past memories for a query.

    Uses domain-scoped user_id so the sales agent only recalls sales patterns,
    the inventory agent only recalls inventory patterns, etc.
    """
    mem = _get_mem0()
    if mem is None:
        return []

    if session_id:
        user_id = session_id
    elif domain:
        user_id = f"ecommerce-{domain}"
    else:
        user_id = "ecommerce-ops"

    try:
        results = mem.search(query, filters={"user_id": user_id}, top_k=limit)
        memories = []
        for item in results.get("results", results) if isinstance(results, dict) else results:
            if isinstance(item, dict):
                memories.append({
                    "memory": item.get("memory", item.get("text", "")),
                    "score": item.get("score", 0.0),
                    "metadata": item.get("metadata", {}),
                })
            else:
                memories.append({
                    "memory": str(item),
                    "score": 0.0,
                    "metadata": {},
                })
        log.info("mem0.recall", query_preview=query[:50], results=len(memories))
        return memories
    except Exception as exc:
        log.error("mem0.recall_failed", error=str(exc)[:200])
        return []
