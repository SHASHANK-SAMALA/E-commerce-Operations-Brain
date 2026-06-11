"""Shared LLM factories — one model per task tier.

Model strategy (token cost vs quality):
  routing_llm()    → gpt-4o-mini  temp=0.0   LLM fallback routing (~5% of queries)
  agent_llm()      → gpt-4o       temp=0.15  Domain analysis (sales/inv/mkt/support)
  synthesis_llm()  → gpt-4o       temp=0.2   Root cause narrative synthesis
  embedding_client()→ all-MiniLM-L6-v2 (local) pgvector semantic search
"""

from __future__ import annotations

from langchain_openai import AzureChatOpenAI

from ecommerce_brain.config.settings import settings

_TIMEOUT = settings.llm_request_timeout
_RETRIES = 2

# Local embedding model (384-dim, runs on CPU, no API key needed)
_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output dimension


def _base_kwargs() -> dict:
    return {
        "azure_endpoint": settings.azure_openai_endpoint,
        "api_key": settings.azure_openai_api_key,
        "api_version": settings.azure_openai_api_version,
        "timeout": _TIMEOUT,
        "max_retries": _RETRIES,
    }


def routing_llm() -> AzureChatOpenAI:
    """Routing fallback — always uses the main gpt-4o deployment (no mini retry penalty)."""
    return AzureChatOpenAI(
        **_base_kwargs(),
        azure_deployment=settings.azure_openai_model,
        temperature=0.0,
    )


def _routing_llm_invoke(messages):
    """Invoke routing LLM."""
    return routing_llm().invoke(messages)


def agent_llm(*, temperature: float = 0.15) -> AzureChatOpenAI:
    """gpt-4o — domain analysis. Quality reasoning over structured data."""
    return AzureChatOpenAI(
        **_base_kwargs(),
        azure_deployment=settings.azure_openai_model,
        temperature=temperature,
    )


def synthesis_llm() -> AzureChatOpenAI:
    """gpt-4o — root cause synthesis. Slightly higher temp for coherent narrative."""
    return AzureChatOpenAI(
        **_base_kwargs(),
        azure_deployment=settings.azure_openai_model,
        temperature=0.2,
    )


_embedding_instance = None


def embedding_client():
    """all-MiniLM-L6-v2 — local embedding model for pgvector semantic search.

    Uses SentenceTransformer directly (not the LangChain wrapper) to guarantee
    the model is loaded exactly ONCE per process — not once per call.
    Returns a thin adapter with .embed_query() / .embed_documents() methods.
    """
    global _embedding_instance
    if _embedding_instance is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_EMBEDDING_MODEL)

        class _EmbedAdapter:
            """Minimal LangChain-compatible wrapper around a loaded SentenceTransformer."""

            def embed_query(self, text: str) -> list[float]:
                return _model.encode(text, normalize_embeddings=True).tolist()

            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                vecs = _model.encode(texts, normalize_embeddings=True)
                return [v.tolist() for v in vecs]

        _embedding_instance = _EmbedAdapter()
    return _embedding_instance
