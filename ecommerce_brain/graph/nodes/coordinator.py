"""Coordinator node — rules routing + LLM fallback (only when confidence < 0.7)."""

from __future__ import annotations

import json

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from opentelemetry import trace

from ecommerce_brain.agents.registry import get_agent
from ecommerce_brain.graph.routing.rules_engine import route
from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.schemas.routing import RoutingDecision

log = structlog.get_logger(__name__)
_tracer = trace.get_tracer("ecommerce_brain.coordinator")

_ROUTING_QUERY_TEMPLATE = (
    "Query: {query}\n\n"
    "Return ONLY valid JSON matching this schema:\n"
    '{{\n'
    '  "intent": "diagnose" | "action" | "memory_query" | "report",\n'
    '  "domains_required": list of "sales" | "inventory" | "marketing" | "support",\n'
    '  "routing_confidence": 0.0-1.0,\n'
    '  "routing_source": "llm_fallback"\n'
    '}}'
)


def coordinator_node(state: GraphState) -> dict:
    with _tracer.start_as_current_span("coordinator_node") as span:
        query = state["query"]
        span.set_attribute("query_id", state.get("query_id", ""))

        # Stage 1: deterministic rules engine (0 tokens, microseconds)
        decision = route(query)

        # Stage 2: LLM fallback only when rules confidence is low
        if decision.routing_confidence < 0.7:
            log.info("coordinator.llm_fallback", query_preview=query[:50])
            from ecommerce_brain.llm import _routing_llm_invoke
            spec = get_agent("coordinator")
            messages = [
                SystemMessage(content=spec.system_prompt),
                HumanMessage(content=_ROUTING_QUERY_TEMPLATE.format(query=query)),
            ]
            try:
                response = _routing_llm_invoke(messages)
                raw = response.content.strip()
                # Strip markdown code fences if present
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                data = json.loads(raw)
                data["routing_source"] = "llm_fallback"
                # Normalise non-standard intent values the LLM sometimes returns.
                _INTENT_ALIASES: dict[str, str] = {
                    "monitor": "diagnose",
                    "analyze": "diagnose",
                    "analyse": "diagnose",
                    "check": "diagnose",
                    "track": "diagnose",
                    "watch": "diagnose",
                    "investigate": "diagnose",
                }
                if "intent" in data:
                    data["intent"] = _INTENT_ALIASES.get(data["intent"], data["intent"])
                decision = RoutingDecision.model_validate(data)
            except Exception as exc:
                log.warning("coordinator.llm_fallback_failed", error=str(exc))
                # Fall back to full investigation
                decision = RoutingDecision(
                    intent="diagnose",
                    domains_required=["sales", "inventory", "marketing", "support"],
                    routing_confidence=0.5,
                    routing_source="llm_fallback",
                )

        span.set_attribute("intent", decision.intent)
        span.set_attribute("routing_confidence", decision.routing_confidence)
        span.set_attribute("routing_source", decision.routing_source)
        span.set_attribute("domains", ",".join(decision.domains_required))

        log.info(
            "coordinator.routed",
            intent=decision.intent,
            domains=decision.domains_required,
            confidence=decision.routing_confidence,
            source=decision.routing_source,
        )

        return {
            "routing_decision": decision,
            "intent": decision.intent,
            "domains_required": decision.domains_required,
            "routing_confidence": decision.routing_confidence,
            "hitl_status": "pending",
            "loop_count": state.get("loop_count", 0),
            "audit_log": [
                {
                    "node": "coordinator",
                    "event": "routed",
                    "intent": decision.intent,
                    "domains": decision.domains_required,
                    "source": decision.routing_source,
                    "confidence": decision.routing_confidence,
                }
            ],
        }
