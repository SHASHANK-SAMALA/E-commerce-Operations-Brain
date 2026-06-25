"""Observability — OpenTelemetry setup + structlog JSON config."""

from __future__ import annotations

import logging

import structlog
from opentelemetry import metrics, trace
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import start_http_server

from ecommerce_brain.config.settings import get_settings

# ── Public tracer / meter used by graph nodes ─────────────────────────────────
tracer = trace.get_tracer("ecommerce_brain")
meter = metrics.get_meter("ecommerce_brain")

# Prometheus counters / histograms (safe to import before setup_otel() because
# the SDK creates no-op instruments until a real MeterProvider is set.)
investigation_counter = meter.create_counter(
    "investigations_total",
    description="Total number of investigations processed",
)
reinvestigation_counter = meter.create_counter(
    "reinvestigations_total",
    description="Total reflection-triggered reinvestigations",
)
evidence_score_histogram = meter.create_histogram(
    "evidence_score",
    description="Distribution of reflection evidence scores",
    unit="1",
)
llm_latency_histogram = meter.create_histogram(
    "llm_call_latency_ms",
    description="LLM call latency in milliseconds",
    unit="ms",
)
agent_call_counter = meter.create_counter(
    "domain_agent_calls_total",
    description="Total domain agent invocations by domain",
)
agent_latency_histogram = meter.create_histogram(
    "domain_agent_latency_ms",
    description="Domain agent execution latency by domain",
    unit="ms",
)


def setup_logging() -> None:
    """Configure structlog with JSON output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
    )

    # Silence LangGraph checkpoint deserialisation warnings for first-party types.
    logging.getLogger("langgraph.checkpoint").setLevel(logging.ERROR)
    logging.getLogger("langgraph.checkpoint.postgres").setLevel(logging.ERROR)

    import warnings

    warnings.filterwarnings(
        "ignore",
        message="Deserializing unregistered type",
        category=UserWarning,
    )


def setup_otel() -> None:
    """Configure OpenTelemetry tracing + Prometheus metrics."""
    s = get_settings()
    if not s.otel_enabled:
        return

    # ── Tracing — attach a span exporter so spans are NOT silently dropped ────
    resource = Resource(attributes={"service.name": s.otel_service_name})
    tracer_provider = TracerProvider(resource=resource)

    # Try OTLP gRPC first (requires opentelemetry-exporter-otlp-proto-grpc).
    # Fall back to ConsoleSpanExporter which is always available in the SDK.
    # importlib avoids a static import that mypy would flag when the package is absent.
    try:
        import importlib
        _otlp = importlib.import_module(
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter"
        )
        span_exporter = _otlp.OTLPSpanExporter(
            endpoint=s.otel_endpoint, insecure=True
        )
    except ImportError:
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter
        span_exporter = ConsoleSpanExporter()

    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    # ── Metrics → Prometheus ──────────────────────────────────────────────────
    reader = PrometheusMetricReader()
    metrics_provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(metrics_provider)
    start_http_server(s.prometheus_port)


def setup_langsmith() -> None:
    """Enable LangSmith tracing if configured.

    Idempotent — safe to call multiple times; will not overwrite values that
    have already been set by a previous call or by the environment directly.
    """
    import os
    s = get_settings()
    api_key = s.langchain_api_key.get_secret_value() if s.langchain_api_key else ""
    if s.langchain_tracing_v2 and api_key:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_API_KEY", api_key)
        os.environ.setdefault("LANGCHAIN_PROJECT", s.langchain_project)


def setup_all() -> None:
    setup_logging()
    setup_otel()
    setup_langsmith()
