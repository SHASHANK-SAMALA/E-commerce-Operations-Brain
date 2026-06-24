"""Shared LLM factories — one model per task tier.

Model strategy (token cost vs quality):
  routing_llm()     → gpt-4o  temp=0.0   LLM fallback routing (~5% of queries)
  agent_llm()       → gpt-4o  temp=0.15  Domain analysis (sales/inv/mkt/support)
  synthesis_llm()   → gpt-4o  temp=0.2   Root cause narrative synthesis
  embedding_client()→ text-embedding-3-small  Azure OpenAI pgvector semantic search
"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

from ecommerce_brain.config.settings import settings

_TIMEOUT = settings.llm_request_timeout
_RETRIES = 2

EMBEDDING_DIM = 1536


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


@lru_cache(maxsize=1)
def embedding_client() -> AzureOpenAIEmbeddings:
    """Azure OpenAI text-embedding-3-small — 1536-dim pgvector semantic search.

    Cached singleton: one client per process.
    """
    return AzureOpenAIEmbeddings(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        azure_deployment=settings.azure_openai_embedding_model,
        timeout=_TIMEOUT,
        max_retries=_RETRIES,
    )
