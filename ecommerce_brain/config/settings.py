"""Application configuration — loaded from .env.

Copy .env.example to .env and fill in your credentials.
All secrets come from environment variables; never hardcoded.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: SecretStr = SecretStr("")
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_model: str = "gpt-4o"
    azure_openai_embedding_model: str = "text-embedding-3-small-1"
    azure_openai_whisper_deployment: str = "whisper"

    # Database
    database_url: str = "postgresql://ecommerce:ecommerce@localhost:5432/ecommerce_brain"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API Security
    api_key: SecretStr = SecretStr("dev-key-change-in-production")
    api_key_header: str = "X-API-Key"

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: SecretStr = SecretStr("")
    langchain_project: str = "ecommerce-brain"

    # OpenTelemetry — falls back to console exporter when no OTLP collector is reachable.
    otel_enabled: bool = True
    otel_service_name: str = "ecommerce-brain"
    otel_endpoint: str = "http://tempo:4317"
    prometheus_port: int = 9091

    # Server
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000

    # CORS — override in production to list your actual frontend origin(s)
    cors_allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # LLM
    llm_request_timeout: int = 90
    max_tokens_per_investigation: int = 12000

    # MCP server URLs (override in docker via env)
    mcp_sales_url: str = "http://localhost:8001/sse"
    mcp_inventory_url: str = "http://localhost:8002/sse"
    mcp_marketing_url: str = "http://localhost:8003/sse"
    mcp_support_url: str = "http://localhost:8004/sse"
    mcp_action_url: str = "http://localhost:8005/sse"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton.

    The cache is intentionally global — settings are immutable after startup.
    Call ``get_settings.cache_clear()`` in tests that need different values.
    """
    return Settings()


settings = get_settings()
