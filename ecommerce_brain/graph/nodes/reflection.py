"""Reflection node — deterministic evidence_score, NO LLM."""
from __future__ import annotations

import structlog
from opentelemetry import trace

from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.schemas.outputs import ReflectionResult

log = structlog.get_logger(__name__)
_tracer = trace.get_tracer("ecommerce_brain.reflection")

_REQUIRED_DOMAINS: dict[str, list[str]] = {
    "diagnose": ["sales", "inventory", "marketing", "support"],
    "action":   ["sales", "inventory"],
    "memory_query": [],
    "report":   ["sales", "inventory", "marketing", "support"],
}

# Signal weights — must sum to 1.0
W_COVERAGE   = 0.4   # did all domains return data?
W_SALES_DROP = 0.2   # how big was the revenue drop?
W_STOCKOUTS  = 0.2   # how many stockouts?
W_CAMPAIGNS  = 0.1   # how many paused campaigns?
W_COMPLAINTS = 0.1   # was there a complaint spike?


def _compute_evidence_score(domains_required: list[str], reports: dict) -> float:
    """How much signal do we actually have? Returns 0.0 – 1.0."""
    domains_with_data = [d for d in domains_required if reports.get(d) is not None]
    coverage = len(domains_with_data) / max(len(domains_required), 1)
    score = coverage * W_COVERAGE

    sales = reports.get("sales")
    if sales and hasattr(sales, "revenue_delta_pct"):
        score += min(abs(sales.revenue_delta_pct) / 100, W_SALES_DROP)

    inventory = reports.get("inventory")
    if inventory and hasattr(inventory, "stockouts"):
        score += min(len(inventory.stockouts) * 0.05, W_STOCKOUTS)

    marketing = reports.get("marketing")
    if marketing and hasattr(marketing, "paused_campaigns"):
        score += min(len(marketing.paused_campaigns) * 0.05, W_CAMPAIGNS)

    support = reports.get("support")
    if support and hasattr(support, "complaint_spike") and support.complaint_spike:
        score += W_COMPLAINTS

    return round(min(1.0, score), 3)


def _should_reinvestigate(
    intent: str,
    evidence_score: float,
    loop_count: int,
    domains_missing: list[str],
) -> bool:
    """Single place that owns the reinvestigation decision."""
    if loop_count >= 2:
        return False                         # hard stop
    if intent == "memory_query":
        return False                         # no agents run — retrying is pointless
    if evidence_score == 0.0:
        return loop_count < 1               # one retry if every agent failed
    # only retry if score is low AND there are missing domains to fetch
    # (if nothing is missing, re-running same agents gives same result)
    return evidence_score < 0.7 and len(domains_missing) > 0


def reflection_node(state: GraphState) -> dict:
    with _tracer.start_as_current_span("reflection_node") as span:
        intent = state.get("intent", "diagnose")
        # Trust what the coordinator already decided; only fall back to the full-domain
        # list when the coordinator wrote nothing (e.g. first-boot edge case).
        domains_required = state.get("domains_required") or _REQUIRED_DOMAINS.get(intent, [])

        reports = {
            "sales":     state.get("sales_report"),
            "inventory": state.get("inventory_report"),
            "marketing": state.get("marketing_report"),
            "support":   state.get("support_report"),
        }

        domains_with_data = [d for d in domains_required if reports.get(d) is not None]
        domains_missing   = [d for d in domains_required if reports.get(d) is None]

        evidence_score       = _compute_evidence_score(domains_required, reports)
        loop_count           = state.get("loop_count", 0)
        should_reinvestigate = _should_reinvestigate(
            intent, evidence_score, loop_count, domains_missing
        )

        span.set_attribute("intent", intent)
        span.set_attribute("evidence_score", evidence_score)
        span.set_attribute("loop_count", loop_count)
        span.set_attribute("should_reinvestigate", should_reinvestigate)

        # Record Prometheus histogram (no-op when otel not enabled)
        try:
            from ecommerce_brain.observability.setup import (
                evidence_score_histogram,
                reinvestigation_counter,
            )
            evidence_score_histogram.record(evidence_score, {"intent": intent})
            if should_reinvestigate:
                reinvestigation_counter.add(1, {"intent": intent})
        except Exception:
            pass

        result = ReflectionResult(
            domains_checked=domains_required,
            domains_with_data=domains_with_data,
            domains_missing=domains_missing,
            evidence_score=evidence_score,
            gaps=[f"No data from {d} domain" for d in domains_missing],
            should_reinvestigate=should_reinvestigate,
            reinvestigate_domains=domains_missing if should_reinvestigate else [],
        )

        log.info(
            "reflection.done",
            evidence_score=evidence_score,
            loop_count=loop_count,
            should_reinvestigate=should_reinvestigate,
        )

        return {
            "reflection_result": result,
            "loop_count":        loop_count + (1 if should_reinvestigate else 0),
            "audit_log": [{
                "node":             "reflection",
                "event":            "scored",
                "evidence_score":   evidence_score,
                "domains_with_data": domains_with_data,
                "domains_missing":  domains_missing,
                "should_reinvestigate": should_reinvestigate,
            }],
        }
