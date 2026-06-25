"""Shared embedding utility — single call site for all vector embeddings.

Both KEDB and incident-store writes use this to avoid duplicating the
embedding_client().embed_query() pattern across modules.
"""

from __future__ import annotations

import structlog

from ecommerce_brain.exceptions import EmbeddingError

log = structlog.get_logger(__name__)


def embed_text(text: str) -> list[float]:
    """Embed *text* using the configured Azure OpenAI embedding model.

    Args:
        text: Plain text to embed. Should be <= ~8000 tokens.

    Returns:
        1536-dimensional float list.

    Raises:
        EmbeddingError: If the embedding client is unavailable or the API call
            fails (missing credentials, network error, timeout).
    """
    try:
        from ecommerce_brain.llm import embedding_client

        return embedding_client().embed_query(text)
    except EmbeddingError:
        raise
    except Exception as exc:
        log.warning("embeddings.embed_failed", error=str(exc)[:200])
        raise EmbeddingError(str(exc)) from exc
