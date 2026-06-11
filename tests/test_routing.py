"""Tests for the routing rules engine."""

from __future__ import annotations

import pytest

from ecommerce_brain.graph.routing.rules_engine import route

# (query, expected_intent, expected_domains_subset)
ROUTING_CASES = [
    ("Why did revenue drop yesterday?", "diagnose", {"sales", "inventory", "marketing", "support"}),
    ("What's our daily revenue?", "diagnose", {"sales"}),
    ("Which products are out of stock?", "diagnose", {"inventory"}),
    ("Show me paused campaigns", "diagnose", {"marketing"}),
    ("Why are customers complaining?", "diagnose", {"support"}),
    ("Restock product SKU-001", "action", {"inventory"}),
    ("What caused last week's outage?", "memory_query", set()),
    ("Generate weekly business report", "report", set()),
]


@pytest.mark.parametrize("query,expected_intent,domains_subset", ROUTING_CASES)
def test_rules_engine_routing(query, expected_intent, domains_subset):
    decision = route(query)
    assert decision.intent == expected_intent
    if domains_subset:
        assert domains_subset.issubset(set(decision.domains_required)), (
            f"Expected {domains_subset} in {decision.domains_required}"
        )


def test_high_confidence_for_clear_queries():
    decision = route("show me the revenue for last 7 days")
    assert decision.routing_confidence >= 0.7


def test_fallback_domain_has_low_confidence():
    """Ambiguous query should fall through with low confidence triggering LLM."""
    decision = route("xyzzy frobulate the business thingamajig")
    assert decision.routing_confidence <= 0.5


def test_routing_source():
    decision = route("Why are sales down?")
    assert decision.routing_source == "rules_engine"
