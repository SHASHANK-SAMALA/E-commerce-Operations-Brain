"""Shared embedding utility — single call site for all vector embeddings.

Both KEDB and incident-store writes use this to avoid duplicating the
embedding_client().embed_query() pattern across modules.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


def embed_text(text: str) -> list[float] | None:
    """Embed *text* using the configured Azure OpenAI embedding model.

    Returns the embedding vector on success, or ``None`` if the client is
    unavailable (missing credentials, network error). Callers must handle
    ``None`` gracefully — the embedding is optional for all write paths.

    Args:
        text: Plain text to embed. Should be <= ~8000 tokens.

    Returns:
        1536-dimensional float list, or ``None`` on failure.
    """
    try:
        from ecommerce_brain.llm import embedding_client

        return embedding_client().embed_query(text)
    except Exception as exc:
        log.warning("embeddings.embed_failed", error=str(exc)[:200])
        return None
