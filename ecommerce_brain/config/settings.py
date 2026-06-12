"""Application configuration — loaded from .env.

Copy .env.example to .env and fill in your credentials.
All secrets come from environment variables; never hardcoded.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Azure OpenAI (same endpoint pattern as Langraph_MCP) ─────────────────
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_model: str = "gpt-4o"
    # Set AZURE_OPENAI_MODEL_MINI in .env only if you have a separate mini deployment.
    # Leave blank to share the same deployment as azure_openai_model.
    azure_openai_model_mini: str = ""
    azure_openai_embedding_model: str = "text-embedding-3-small"
    azure_openai_whisper_deployment: str = "whisper"

    @model_validator(mode="after")
    def _resolve_mini_model(self) -> Settings:
        """Clear azure_openai_model_mini if it looks like an undeployed stock model name.
        This prevents 'Unknown deployment: gpt-4o-mini' errors when the user copied the
        example value but never created that Azure deployment.
        Tier-2 guardrail and coordinator fallback will then use the main model instead.
        """
        # If mini is blank or identical to main, nothing to do.
        if not self.azure_openai_model_mini:
            return self
        if self.azure_openai_model_mini == self.azure_openai_model:
            self.azure_openai_model_mini = ""
            return self
        return self

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql://ecommerce:ecommerce@localhost:5432/ecommerce_brain"

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── API Security ──────────────────────────────────────────────────────────
    api_key: str = "dev-key-change-in-production"
    api_key_header: str = "X-API-Key"

    # ── LangSmith ─────────────────────────────────────────────────────────────
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "ecommerce-brain"

    # ── OpenTelemetry ─────────────────────────────────────────────────────────
    # Default ON: FastAPI HTTP traces + Prometheus metrics work out of the box.
    # If no OTLP collector is reachable the SDK falls back to a console exporter.
    # Override to false in tests / CI by setting OTEL_ENABLED=false in env.
    otel_enabled: bool = True
    otel_service_name: str = "ecommerce-brain"
    otel_endpoint: str = "http://tempo:4317"   # OTLP gRPC collector endpoint
    prometheus_port: int = 9090

    # ── Server ────────────────────────────────────────────────────────────────
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000

    # ── LLM Cost / Token Control ──────────────────────────────────────────────
    llm_request_timeout: int = 90
    max_tokens_per_investigation: int = 12000

    # ── Routing fallback (optional Mistral via Ollama) ─────────────────────────
    use_local_routing_llm: bool = False
    ollama_base_url: str = "http://localhost:11434"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
