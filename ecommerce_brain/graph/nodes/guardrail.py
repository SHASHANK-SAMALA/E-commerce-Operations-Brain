"""Guardrail node — first node in graph. Blocks on injection/invalid input.

Two-tier relevance check (runs after length/injection checks):
  Tier 1 — regex/keyword (~0 ms): obvious off-topic queries rejected immediately.
  Tier 2 — LLM classification (~1 s): called only for ambiguous cases.

The existing _guardrail_edge in graph.py already routes to END when
blocked_reason is set, so no graph wiring changes are needed.
"""

from __future__ import annotations

import json
import re
import time
from typing import Literal

import structlog
from opentelemetry import trace

from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.guardrails.prompt_injection import InjectionDetected, check_for_injection

_tracer = trace.get_tracer("ecommerce_brain.guardrail")

log = structlog.get_logger(__name__)

# ── Tier 1: fast pattern matching ─────────────────────────────────────────────

_REJECT_PATTERNS: list[re.Pattern] = [
    # Food / cooking
    re.compile(
        r"\b(cook|recipe|ingredient|bake|boil|fry|grill|roast|steam|cuisine|burger|pizza|pasta)\b",
        re.I,
    ),
    # Weather
    re.compile(r"\b(weather|temperature|rain|sunny|forecast|climate|humidity)\b", re.I),
    # Entertainment
    re.compile(
        r"\b(movie|song|music|artist|actor|film|tv\s*show|series|lyrics|album|singer|band|concert)\b",
        re.I,
    ),
    # Sports (names are caught via 'who is' pattern below)
    re.compile(
        r"\b(cricket|football|soccer|basketball|tennis|sports\s+score|match\s+result|batsman|wicket|scorer)\b",
        re.I,
    ),
    # Geography / politics
    re.compile(
        r"\b(capital\s+city|geography|history\s+of|war|politics|parliament|election)\b",
        re.I,
    ),
    # Creative / general knowledge requests
    re.compile(r"\b(joke|funny|poem|riddle|write\s+me\s+a|tell\s+me\s+a\s+story)\b", re.I),
    # Language queries
    re.compile(r"\b(translate|grammar|definition\s+of|meaning\s+of|synonym|antonym)\b", re.I),
    # General knowledge person / entity lookups — "who is X", "who was X"
    # NOTE: allow keywords are checked BEFORE reject patterns, so
    # "who is responsible for the sales drop?" won't reach this pattern.
    re.compile(r"\bwho\s+(is|was|are|were)\b", re.I),
    re.compile(r"\bwhat\s+is\s+(a|an)\b", re.I),
    re.compile(
        r"\b(biography|birthdate|born\s+in|nationality|famous\s+for|known\s+for|net\s+worth)\b",
        re.I,
    ),
    re.compile(r"\b(president|prime\s+minister|ceo\s+of|founder\s+of|country\s+of)\b", re.I),
]

_ECOMMERCE_ALLOW_KEYWORDS: frozenset[str] = frozenset({
    # Business metrics — highly domain-specific
    "revenue", "sales", "orders", "aov", "conversion", "gmv", "profit",
    "decline", "declining", "drop", "performance",
    # Inventory — highly domain-specific
    "stock", "stockout", "sku", "restock", "inventory", "warehouse",
    "supplier", "reorder", "backorder", "fulfillment", "product",
    # Marketing metrics — acronyms are unambiguous
    "roas", "cpa", "cpc", "ads", "spend", "campaign",
    "discount", "promotion", "flash", "category",
    # Commerce-specific support terms
    "refund", "return", "chargeback", "shipping", "defect",
    "complaint", "customer", "ticket",
    # Commerce object words
    "checkout", "cart", "listing", "marketplace", "seller", "buyer",
    # Business reporting — summary/health/report queries
    "report", "summary", "health", "business", "incident", "overview",
})

_REJECTION_RESPONSE = (
    "⚠️  This system only handles e-commerce operations queries.\n\n"
    "Please ask something like:\n"
    "  • \"Why did revenue drop last week?\"\n"
    "  • \"Which SKUs are near stockout?\"\n"
    "  • \"Are any ad campaigns paused?\"\n"
    "  • \"What's causing the support ticket spike?\""
)


def _tier1_classify(query: str) -> Literal["reject", "allow", "uncertain"]:
    q_lower = query.lower()

    # Check e-commerce allow keywords FIRST — this overrides reject patterns.
    # Use \b + prefix matching so "campaign" matches "campaigns", "order" matches "orders", etc.
    if any(re.search(r"\b" + re.escape(kw), q_lower) for kw in _ECOMMERCE_ALLOW_KEYWORDS):
        return "allow"

    query_words = set(re.findall(r"\w+", q_lower))

    # Hard reject: matches a known off-topic pattern
    for pattern in _REJECT_PATTERNS:
        if pattern.search(q_lower):
            return "reject"

    # Very short queries (≤ 3 tokens) are likely business commands; let coordinator decide.
    if len(query_words) <= 3:
        return "allow"

    return "uncertain"


# ── Tier 2: LLM classification (uncertain cases only) ─────────────────────────

_GUARDRAIL_SYSTEM_PROMPT = (
    "You are a strict input classifier for an e-commerce operations AI.\n"
    "Respond ONLY with valid JSON: {\"relevant\": true} or {\"relevant\": false}\n\n"
    "Relevant = the query is about e-commerce operations: sales metrics, inventory,\n"
    "marketing campaigns, customer support, orders, shipping, products, or business performance.\n"
    "Not relevant = cooking, weather, sports, entertainment, geography, general knowledge, etc."
)


def _tier2_llm_classify(query: str) -> bool:
    """Returns True if relevant, False if off-topic.

    On LLM error: fails CLOSED (rejects) because Tier 2 is only reached when
    the query has NO e-commerce keywords — so uncertain + broken LLM means
    we cannot confirm relevance and should not run the full agent pipeline.
    """
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from ecommerce_brain.llm import routing_llm  # lazy import to avoid circular deps
        response = routing_llm().invoke([
            SystemMessage(content=_GUARDRAIL_SYSTEM_PROMPT),
            HumanMessage(content=query),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(raw)
        return bool(result.get("relevant", False))
    except Exception as exc:
        # Fail closed: query reached Tier 2 because it had no e-commerce keywords.
        # When the LLM is unavailable we cannot confirm relevance, so reject.
        log.warning("guardrail.tier2_failed_closed", error=str(exc), query_preview=query[:60])
        return False


# ── Node ──────────────────────────────────────────────────────────────────────

def guardrail_node(state: GraphState) -> dict:
    with _tracer.start_as_current_span("guardrail_node") as span:
        return _guardrail_node_impl(state, span)


def _guardrail_node_impl(state: GraphState, span) -> dict:  # noqa: ANN001
    start_ms = int(time.time() * 1000)
    query = state["query"]
    query_id = state.get("query_id", "unknown")
    span.set_attribute("query_id", query_id)

    log.info("graph.event", node="guardrail", query_id=query_id)

    # 1. Length check
    if len(query.strip()) < 3:
        span.set_attribute("blocked_reason", "input_too_short")
        return {
            "error": "Query too short",
            "blocked_reason": "input_too_short",
            "investigation_start_ms": start_ms,
            "audit_log": [{"node": "guardrail", "event": "blocked", "reason": "input_too_short"}],
        }

    if len(query) > 2000:
        span.set_attribute("blocked_reason", "input_too_long")
        return {
            "error": "Query exceeds 2000 character limit",
            "blocked_reason": "input_too_long",
            "investigation_start_ms": start_ms,
            "audit_log": [{"node": "guardrail", "event": "blocked", "reason": "input_too_long"}],
        }

    # 2. Prompt injection check
    try:
        check_for_injection(query, source="user_input")
    except InjectionDetected as e:
        span.set_attribute("blocked_reason", "prompt_injection")
        return {
            "error": f"Input blocked: potential prompt injection ({e.pattern_label})",
            "blocked_reason": "prompt_injection",
            "investigation_start_ms": start_ms,
            "audit_log": [
                {
                    "node": "guardrail",
                    "event": "blocked",
                    "reason": "prompt_injection",
                    "pattern_label": e.pattern_label,
                    "is_security_event": True,
                }
            ],
        }

    # 3. Tier 1: instant regex/keyword relevance check
    t1_result = _tier1_classify(query)

    if t1_result == "reject":
        log.info("guardrail.rejected", tier=1, query_preview=query[:80], query_id=query_id)
        span.set_attribute("blocked_reason", "off_topic")
        span.set_attribute("tier", 1)
        return {
            "error": _REJECTION_RESPONSE,
            "blocked_reason": "off_topic",
            "investigation_start_ms": start_ms,
            "audit_log": [
                {"node": "guardrail", "event": "blocked", "reason": "off_topic", "tier": 1}
            ],
        }

    if t1_result == "allow":
        log.info("guardrail.passed", tier=1, query_preview=query[:80])
        span.set_attribute("passed", True)
        span.set_attribute("tier", 1)
        return {
            "investigation_start_ms": start_ms,
            "audit_log": [
                {"node": "guardrail", "event": "passed", "tier": 1, "query_length": len(query)}
            ],
        }

    # 4. Tier 2: LLM check for uncertain cases
    log.info("guardrail.tier2_check", query_preview=query[:80])
    is_relevant = _tier2_llm_classify(query)

    if not is_relevant:
        log.info("guardrail.rejected", tier=2, query_preview=query[:80], query_id=query_id)
        span.set_attribute("blocked_reason", "off_topic")
        span.set_attribute("tier", 2)
        return {
            "error": _REJECTION_RESPONSE,
            "blocked_reason": "off_topic",
            "investigation_start_ms": start_ms,
            "audit_log": [
                {"node": "guardrail", "event": "blocked", "reason": "off_topic", "tier": 2}
            ],
        }

    log.info("guardrail.passed", tier=2, query_preview=query[:80])
    span.set_attribute("passed", True)
    span.set_attribute("tier", 2)
    return {
        "investigation_start_ms": start_ms,
        "audit_log": [
            {"node": "guardrail", "event": "passed", "tier": 2, "query_length": len(query)}
        ],
    }
