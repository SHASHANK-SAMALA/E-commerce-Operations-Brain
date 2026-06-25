"""No-op-safe wrappers for OpenTelemetry / Prometheus metric calls.

Metric emission must never crash the graph. OTel SDK instruments are already
no-ops when no MeterProvider is configured, but can still raise if the SDK
itself is misconfigured or partially initialised. These helpers absorb those
errors with a single log.warning so every call site stays clean with no
try/except boilerplate.

Usage:
    from ecommerce_brain.observability.safe_metrics import safe_add, safe_record
    from ecommerce_brain.observability.setup import agent_call_counter, llm_latency_histogram

    safe_add(agent_call_counter, 1, {"domain": domain})
    safe_record(llm_latency_histogram, elapsed_ms, {"node": "synthesis"})
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)


def safe_add(counter: Any, value: int, attributes: dict | None = None) -> None:
    """Call counter.add(value, attributes), swallowing any SDK error."""
    try:
        counter.add(value, attributes or {})
    except Exception as exc:
        log.warning("metrics.add_failed", counter=type(counter).__name__, error=str(exc))


def safe_record(histogram: Any, value: float, attributes: dict | None = None) -> None:
    """Call histogram.record(value, attributes), swallowing any SDK error."""
    try:
        histogram.record(value, attributes or {})
    except Exception as exc:
        log.warning("metrics.record_failed", histogram=type(histogram).__name__, error=str(exc))
