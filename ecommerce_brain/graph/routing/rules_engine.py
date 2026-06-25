"""Deterministic rules engine — handles ~95% of queries with zero tokens.

RETE-style: ordered rules, first match wins, fallback to LLM on low confidence.
"""

from __future__ import annotations

import re
from typing import Literal

from ecommerce_brain.schemas.routing import RoutingDecision

_Intent = Literal["diagnose", "action", "memory_query", "report"]
_Domain = Literal["sales", "inventory", "marketing", "support"]

# (regex_pattern, domains, intent) — ordered most-specific first
_RULES: list[tuple[str, list[_Domain], _Intent]] = [
    # Memory queries — highest priority
    (r"\b(last\s+time|what\s+did\s+we\s+do|has\s+this\s+happened|happened\s+before)\b", [], "memory_query"),
    (r"\b(last\s+(?:week|month|year)|previously|history|similar\s+incident)\b", [], "memory_query"),

    # Action rules — before diagnose so intent classification is correct
    (r"\b(restock|replenish)\b.*\b(sku|product|item)\b", ["inventory"], "action"),
    (r"\b(restock|replenish)\b", ["inventory"], "action"),
    (r"\b(resume|pause)\b.{0,30}\bcampaigns?\b", ["marketing"], "action"),
    (r"\b(increase|boost).{0,20}\b(budget|spend)\b", ["marketing"], "action"),
    (
        r"\b(apply.{0,10}discount|run.{0,10}discount|discount.{0,10}promotion|flash\s+sale)\b",
        ["sales"],
        "action",
    ),
    (
        r"\b(fix|resolve)\b.{0,40}\b(stock|inventory|sku|out.of.stock|stockouts?)\b",
        ["inventory"],
        "action",
    ),
    (
        r"\b(fix|resolve)\b.{0,40}\b(campaign|ads?|marketing|promotion|roas)\b",
        ["marketing"],
        "action",
    ),
    (
        r"\b(fix|resolve)\b.{0,40}\b(complaint|refund|return|ticket|customer|support)\b",
        ["support"],
        "action",
    ),
    (
        r"\b(fix|resolve)\b.{0,40}\b(sales|revenue|orders?|aov|gmv)\b",
        ["sales"],
        "action",
    ),
    (r"\b(execute|approve)\b", ["sales", "inventory"], "action"),

    # Root cause (multi-domain) diagnose
    (
        r"(complaint|missing\s+order|customer\s+issue).{0,60}(drop|decline|revenue|sales)",
        ["sales", "inventory", "marketing", "support"],
        "diagnose",
    ),
    (
        r"(drop|decline|revenue|sales).{0,60}(complaint|missing\s+order|customer\s+issue)",
        ["sales", "inventory", "marketing", "support"],
        "diagnose",
    ),
    (
        r"why.{0,30}(drop|decline|fell|fall|down|decrease|low|loss)",
        ["sales", "inventory", "marketing", "support"],
        "diagnose",
    ),
    (
        r"(sales|revenue|orders?).{0,20}(drop|decline|fell|fall|down|decrease)",
        ["sales", "inventory", "marketing"],
        "diagnose",
    ),

    # Memory queries (remaining patterns)
    (r"\b(before|past|what\s+caused\s+last)\b", [], "memory_query"),

    # Domain-specific diagnose
    (r"\b(out.of.stock|stockouts?|out_of_stock)\b", ["inventory"], "diagnose"),
    (r"\b(revenue|sales|orders?|aov|average order|gmv)\b", ["sales"], "diagnose"),
    (r"\b(stock|inventory|sku)\b", ["inventory"], "diagnose"),
    (
        r"\b(campaign|ad\b|ads\b|marketing|promotion|roas|paused|impressions)\b",
        ["marketing"],
        "diagnose",
    ),
    (
        r"\b(complaint|complaints?|refund|return|customer|support|ticket|sentiment|review|missing\s+order)\b",
        ["support"],
        "diagnose",
    ),

    # Report
    (
        r"\b(report|summary|overview|dashboard|health|status)\b",
        ["sales", "inventory", "marketing", "support"],
        "report",
    ),
]

_COMPILED: list[tuple[re.Pattern[str], list[_Domain], _Intent]] = [
    (re.compile(p, re.IGNORECASE), domains, intent)
    for p, domains, intent in _RULES
]


def route(query: str) -> RoutingDecision:
    """Match query against ordered rules. Returns RoutingDecision with source=rules_engine.

    The first rule that matches wins. Returns a low-confidence fallback when
    nothing matches so the caller knows to invoke the LLM router instead.

    Args:
        query: Raw user query string.

    Returns:
        RoutingDecision with confidence=0.85 on a rule match, or 0.3 on fallback.
    """
    for pattern, domains, intent in _COMPILED:
        if pattern.search(query):
            unique_domains = list(dict.fromkeys(domains))
            return RoutingDecision(
                intent=intent,
                domains_required=unique_domains,
                routing_confidence=0.85,
                routing_source="rules_engine",
                matched_rule=pattern.pattern[:60],
            )
    else:
        return RoutingDecision(
            intent="diagnose",
            domains_required=["sales", "inventory", "marketing", "support"],
            routing_confidence=0.3,
            routing_source="rules_engine",
            matched_rule=None,
        )
