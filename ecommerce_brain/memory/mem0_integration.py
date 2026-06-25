"""Mem0 integration — semantic memory layer on top of the incident store.

Provides natural language recall for conversational queries like:
  "What did we do last time sales dropped?"
  "Has this happened before?"

Uses pgvector as the vector store backend to stay within existing infrastructure.
"""

from __future__ import annotations

import threading

import structlog

log = structlog.get_logger(__name__)


class _Mem0Singleton:
    """Thread-safe lazy singleton for the Mem0 Memory instance.

    Uses double-checked locking so the heavy initialization only runs once,
    even under concurrent requests at startup.
    """

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get(cls):
        """Return the shared Mem0 Memory instance, initialising lazily."""
        if cls._instance is not None:
            return cls._instance

        with cls._lock:
            if cls._instance is not None:
                return cls._instance

            try:
                from mem0 import Memory

                from ecommerce_brain.config.settings import get_settings

                s = get_settings()

                config = {
                    "vector_store": {
                        "provider": "pgvector",
                        "config": {
                            "connection_string": s.database_url,
                            "collection_name": "mem0_memories",
                            "embedding_model_dims": 1536,
                        },
                    },
                    "embedder": {
                        # Use openai provider — avoids needing azure-identity package.
                        # The EPAM proxy is OpenAI-compatible; we pass api_key + base_url.
                        "provider": "openai",
                        "config": {
                            "model": s.azure_openai_embedding_model,
                            "api_key": s.azure_openai_api_key.get_secret_value(),
                            "openai_base_url": (
                                s.azure_openai_endpoint.rstrip("/")
                                + f"/openai/deployments/{s.azure_openai_embedding_model}"
                            ),
                        },
                    },
                    "llm": {
                        "provider": "openai",
                        "config": {
                            "model": s.azure_openai_model,
                            "api_key": s.azure_openai_api_key.get_secret_value(),
                            "openai_base_url": (
                                s.azure_openai_endpoint.rstrip("/")
                                + f"/openai/deployments/{s.azure_openai_model}"
                            ),
                        },
                    },
                }

                cls._instance = Memory.from_config(config)
                log.info("mem0.initialized")
                return cls._instance
            except ImportError as exc:
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
    """Store a completed investigation as a semantic memory.

    Args:
        query_id: Unique investigation identifier.
        query: Original user query.
        root_causes: List of root cause strings from the report.
        actions_taken: Action types that executed successfully.
        evidence_score: Evidence quality score in [0, 1].
        session_id: If provided, scope the memory to this session.
        domain: If provided, scope the memory to this domain agent.

    Returns:
        True if the memory was added successfully, False otherwise.
    """
    mem = _Mem0Singleton.get()
    if mem is None:
        return False

    summary = (
        f"Investigation '{query}' found root causes: {', '.join(root_causes)}. "
        f"Actions taken: {', '.join(actions_taken) if actions_taken else 'none'}. "
        f"Evidence score: {evidence_score:.2f}."
    )

    if session_id:
        user_id = session_id
    elif domain:
        user_id = f"ecommerce-{domain}"
    else:
        user_id = "ecommerce-ops"

    metadata: dict = {"query_id": query_id, "evidence_score": evidence_score}
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

    Args:
        query: Natural language query to search for.
        session_id: If provided, restrict recall to this session's memories.
        domain: If provided, restrict recall to this domain's memories.
        limit: Maximum number of results to return.

    Returns:
        List of dicts with keys: memory (str), score (float), metadata (dict).
    """
    mem = _Mem0Singleton.get()
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
        memories: list[dict] = []
        for item in results.get("results", results) if isinstance(results, dict) else results:
            if isinstance(item, dict):
                memories.append({
                    "memory": item.get("memory", item.get("text", "")),
                    "score": item.get("score", 0.0),
                    "metadata": item.get("metadata", {}),
                })
            else:
                memories.append({"memory": str(item), "score": 0.0, "metadata": {}})
        log.info("mem0.recall", query_preview=query[:50], results=len(memories))
        return memories
    except Exception as exc:
        log.error("mem0.recall_failed", error=str(exc)[:200])
        return []
