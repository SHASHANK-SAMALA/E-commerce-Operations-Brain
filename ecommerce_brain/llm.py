"""Shared LLM factories — one model per task tier.

Model strategy (token cost vs quality):
  routing_llm()      → gpt-4o  temp=0.0   LLM fallback routing (~5% of queries)
  agent_llm()        → gpt-4o  temp=0.15  Domain analysis (sales/inv/mkt/support)
  synthesis_llm()    → gpt-4o  temp=0.2   Root cause narrative synthesis
  embedding_client() → text-embedding-3-small  pgvector semantic search

All chat-LLM instances are cached by temperature so they are created once per
process rather than on every graph invocation.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

from ecommerce_brain.config.settings import get_settings

EMBEDDING_DIM = 1536

_RETRIES = 2


def _base_kwargs() -> dict:
    s = get_settings()
    return {
        "azure_endpoint": s.azure_openai_endpoint,
        "api_key": s.azure_openai_api_key.get_secret_value(),
        "api_version": s.azure_openai_api_version,
        "timeout": s.llm_request_timeout,
        "max_retries": _RETRIES,
    }


@lru_cache(maxsize=8)
def _get_chat_llm(temperature: float) -> AzureChatOpenAI:
    """Cached AzureChatOpenAI factory keyed by temperature.

    LangChain client objects are stateless and safe to reuse across
    concurrent coroutines, so sharing one instance per temperature is fine.
    """
    return AzureChatOpenAI(
        **_base_kwargs(),
        azure_deployment=get_settings().azure_openai_model,
        temperature=temperature,
    )


def routing_llm() -> AzureChatOpenAI:
    """Routing fallback — temperature 0.0 for deterministic intent classification."""
    return _get_chat_llm(0.0)


def agent_llm(*, temperature: float = 0.15) -> AzureChatOpenAI:
    """Domain analysis LLM — balanced temperature for structured reasoning."""
    return _get_chat_llm(temperature)


def synthesis_llm() -> AzureChatOpenAI:
    """Root-cause synthesis LLM — slightly higher temperature for coherent narrative."""
    return _get_chat_llm(0.2)


@lru_cache(maxsize=1)
def embedding_client() -> AzureOpenAIEmbeddings:
    """Azure OpenAI text-embedding-3-small — 1536-dim pgvector semantic search.

    Cached singleton: one client per process.
    """
    s = get_settings()
    return AzureOpenAIEmbeddings(
        azure_endpoint=s.azure_openai_endpoint,
        api_key=s.azure_openai_api_key.get_secret_value(),
        api_version=s.azure_openai_api_version,
        azure_deployment=s.azure_openai_embedding_model,
        timeout=s.llm_request_timeout,
        max_retries=_RETRIES,
    )
