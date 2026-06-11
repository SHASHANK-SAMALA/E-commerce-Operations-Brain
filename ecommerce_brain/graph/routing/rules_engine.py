"""Deterministic rules engine — handles ~95% of queries with zero tokens.

RETE-style: ordered rules, first match wins, fallback to LLM on low confidence.
"""

from __future__ import annotations

import re

from ecommerce_brain.schemas.routing import RoutingDecision

# (regex_pattern, domains, intent) — ordered most-specific first
_RULES: list[tuple[str, list[str], str]] = [
    # Memory queries — HIGHEST priority when "last time/before/history" is clearly present
    (r"\b(last\s+time|what\s+did\s+we\s+do|has\s+this\s+happened|happened\s+before)\b", [], "memory_query"),  # noqa: E501
    (r"\b(last\s+(?:week|month|year)|previously|history|similar\s+incident)\b", [], "memory_query"),  # noqa: E501
    # Root cause (multi-domain) — broad sales drop; include support when complaints mentioned
    (r"(complaint|missing\s+order|customer\s+issue).{0,60}(drop|decline|revenue|sales)", ["sales", "inventory", "marketing", "support"], "diagnose"),  # noqa: E501
    (r"(drop|decline|revenue|sales).{0,60}(complaint|missing\s+order|customer\s+issue)", ["sales", "inventory", "marketing", "support"], "diagnose"),  # noqa: E501
    (r"why.{0,30}(drop|decline|fell|fall|down|decrease|low|loss)", ["sales", "inventory", "marketing", "support"], "diagnose"),  # noqa: E501
    (r"(sales|revenue|orders?).{0,20}(drop|decline|fell|fall|down|decrease)", ["sales", "inventory", "marketing"], "diagnose"),  # noqa: E501
    # Specific action patterns — narrow domain routing
    (r"\b(restock|replenish)\b.*\b(sku|product|item)\b", ["inventory"], "action"),
    (r"\b(restock|replenish)\b", ["inventory"], "action"),
    (r"\b(resume|pause)\b.{0,30}\bcampaign\b", ["marketing"], "action"),
    (r"\b(increase|boost).{0,20}\b(budget|spend)\b", ["marketing"], "action"),
    (r"\b(apply.{0,10}discount|run.{0,10}discount|discount.{0,10}promotion|flash\s+sale)\b", ["sales"], "action"),  # noqa: E501
    # Generic actions — broader routing when domain unclear
    (r"\b(fix|resolve|execute|approve)\b", ["sales", "inventory"], "action"),
    # Memory queries (catch remaining patterns not caught by top-level memory rules)
    (r"\b(before|past|what\s+caused\s+last)\b", [], "memory_query"),
    # Out-of-stock priority — must be checked before generic "revenue" rule
    # because "out of stock causing revenue loss" should route to inventory.
    (r"\b(out.of.stock|stockout|out_of_stock)\b", ["inventory"], "diagnose"),
    # Pure sales
    (r"\b(revenue|sales|orders?|aov|average order|gmv)\b", ["sales"], "diagnose"),
    # Inventory (remaining stock/sku keywords)
    (r"\b(stock|inventory|sku)\b", ["inventory"], "diagnose"),
    # Marketing
    (r"\b(campaign|ad\b|ads\b|marketing|promotion|roas|paused|impressions)\b", ["marketing"], "diagnose"),  # noqa: E501
    # Support — explicit complaint/missing-order keywords route to support domain
    (r"\b(complaint|complaints?|refund|return|customer|support|ticket|sentiment|review|missing\s+order)\b", ["support"], "diagnose"),  # noqa: E501
    # Report
    (r"\b(report|summary|overview|dashboard|health|status)\b", ["sales", "inventory", "marketing", "support"], "report"),  # noqa: E501
]

_COMPILED: list[tuple[re.Pattern, list[str], str]] = [
    (re.compile(p, re.IGNORECASE), domains, intent)
    for p, domains, intent in _RULES
]


def route(query: str) -> RoutingDecision:
    """Match query against rules. Returns RoutingDecision with source=rules_engine."""
    for pattern, domains, intent in _COMPILED:
        if pattern.search(query):
            # Deduplicate while preserving order
            seen: set[str] = set()
            unique_domains = [d for d in domains if not (d in seen or seen.add(d))]  # type: ignore[func-returns-value]
            return RoutingDecision(
                intent=intent,  # type: ignore[arg-type]
                domains_required=unique_domains,  # type: ignore[arg-type]
                routing_confidence=0.95,
                routing_source="rules_engine",
                matched_rule=pattern.pattern[:60],
            )

    # No rule matched — signal LLM fallback needed
    return RoutingDecision(
        intent="diagnose",
        domains_required=["sales", "inventory", "marketing", "support"],
        routing_confidence=0.3,
        routing_source="rules_engine",
        matched_rule=None,
    )
