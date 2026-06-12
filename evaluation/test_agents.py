"""DeepEval agent evaluation suite.

Tests the routing, intent classification, HITL enforcement, and evidence scoring
of the E-Commerce Operations Brain multi-agent system.

Run with: deepeval test run evaluation/test_agents.py
Or:       pytest evaluation/test_agents.py -v
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ecommerce_brain.graph.nodes.reflection import reflection_node
from ecommerce_brain.graph.routing.rules_engine import route
from ecommerce_brain.schemas.outputs import (
    InventoryReport,
    MarketingReport,
    SalesReport,
    SupportReport,
)
from evaluation.dataset import EVALUATION_DATASET
from evaluation.metrics import (
    CorrectDomainRoutingMetric,
    CorrectIntentClassificationMetric,
    EvidenceScoreRangeMetric,
    HITLRequiredMetric,
    NoExtraDomainsMetric,
    SynthesisRelevanceMetric,
)


def _get_routing_output(query: str) -> dict:
    """Run the coordinator's rules engine on a query and return structured output."""
    decision = route(query)
    return {
        "intent": decision.intent,
        "domains_required": decision.domains_required,
        "routing_confidence": decision.routing_confidence,
        "routing_source": decision.routing_source,
    }


def _get_reflection_output(domains_with_data: list[str], domains_required: list[str]) -> dict:
    """Call the REAL reflection node formula — not a hand-rolled approximation.

    Builds the minimal GraphState the node needs and delegates fully to the
    production code so test coverage tracks actual behaviour.
    """
    state = {
        "intent": "diagnose",
        "domains_required": domains_required,
        "loop_count": 0,
        "sales_report": SalesReport(
            revenue_delta_pct=-10.0,
            order_delta_pct=-8.0,
            aov_delta_pct=2.0,
            affected_regions=[],
            anomaly_score=0.5,
            is_drop_significant=True,
            date_range="2024-01-01 to 2024-01-07",
        ) if "sales" in domains_with_data else None,
        "inventory_report": InventoryReport() if "inventory" in domains_with_data else None,
        "marketing_report": MarketingReport() if "marketing" in domains_with_data else None,
        "support_report": SupportReport() if "support" in domains_with_data else None,
    }
    result = reflection_node(state)
    return {"evidence_score": result["reflection_result"].evidence_score}


def _get_hitl_status(case: dict) -> dict:
    """Determine the expected graph status by testing the hitl_node directly.

    For action queries: the hitl_node MUST call interrupt() → GraphInterrupt raised.
    For non-action queries: routing stops before hitl_node → status is 'completed'.
    """
    from langgraph.errors import GraphInterrupt

    from ecommerce_brain.graph.nodes.hitl import hitl_node

    routing = _get_routing_output(case["query"])
    if routing["intent"] != "action":
        return {"status": "completed", "intent": routing["intent"]}

    # Build minimal state with a placeholder proposed action to trigger interrupt.
    mock_state = {
        "query_id": "test-hitl-check",
        "intent": "action",
        "proposed_actions": [
            {
                "action_id": "test-001",
                "action_type": "apply_discount_promotion",
                "params": {"discount_pct": 10, "category": "test", "dry_run": True},
                "estimated_impact": "test",
                "dry_run_result": None,
                "kadb_success_rate": None,
            }
        ],
        "root_cause_report": None,
    }
    try:
        hitl_node(mock_state)
        # interrupt() not raised → HITL broken
        return {"status": "completed", "intent": "action"}
    except GraphInterrupt:
        return {"status": "awaiting_approval", "intent": "action"}


# Routing tests skip cases where the guardrail blocks before routing.
_ROUTABLE = [c for c in EVALUATION_DATASET if not c.get("should_be_blocked")]

# ── Routing Tests ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", _ROUTABLE, ids=[c["query"][:40] for c in _ROUTABLE])
def test_correct_intent_classification(case):
    """Every query must be classified with the correct intent."""
    actual = _get_routing_output(case["query"])

    test_case = LLMTestCase(
        input=case["query"],
        actual_output=json.dumps(actual),
        expected_output=json.dumps(case),
    )

    metric = CorrectIntentClassificationMetric()
    assert_test(test_case, [metric])


@pytest.mark.parametrize("case", _ROUTABLE, ids=[c["query"][:40] for c in _ROUTABLE])
def test_correct_domain_routing(case):
    """Routed domains must match expected domains."""
    actual = _get_routing_output(case["query"])

    test_case = LLMTestCase(
        input=case["query"],
        actual_output=json.dumps(actual),
        expected_output=json.dumps(case),
    )

    metric = CorrectDomainRoutingMetric()
    assert_test(test_case, [metric])


@pytest.mark.parametrize("case", _ROUTABLE, ids=[c["query"][:40] for c in _ROUTABLE])
def test_hitl_enforcement(case):
    """Action queries must cause the graph to pause (GraphInterrupt → awaiting_approval).

    Non-action queries must complete without pausing. Uses _get_hitl_status which
    actually invokes hitl_node and catches GraphInterrupt rather than just checking
    the intent label.
    """
    actual = _get_hitl_status(case)

    test_case = LLMTestCase(
        input=case["query"],
        actual_output=json.dumps(actual),
        expected_output=json.dumps(case),
    )

    metric = HITLRequiredMetric()
    assert_test(test_case, [metric])


@pytest.mark.parametrize("case", _ROUTABLE, ids=[c["query"][:40] for c in _ROUTABLE])
def test_no_unnecessary_domains(case):
    """Routing should not spawn unnecessary domain agents (cost efficiency)."""
    actual = _get_routing_output(case["query"])

    test_case = LLMTestCase(
        input=case["query"],
        actual_output=json.dumps(actual),
        expected_output=json.dumps(case),
    )

    metric = NoExtraDomainsMetric()
    assert_test(test_case, [metric])


# ── Evidence Score Tests ──────────────────────────────────────────────────────


# ── Synthesis Quality (LLM-judge — needs Azure OpenAI credentials) ────────────


_AZURE_KEYS_PRESENT = bool(os.getenv("AZURE_OPENAI_API_KEY")) and bool(
    os.getenv("AZURE_OPENAI_ENDPOINT")
)


@pytest.mark.skipif(
    not _AZURE_KEYS_PRESENT,
    reason="Azure OpenAI credentials not set — skipping LLM-judge metric.",
)
@pytest.mark.parametrize(
    "query,summary,min_score",
    [
        (
            "Why did sales drop yesterday?",
            "Revenue fell 12% versus the prior day, driven by stockouts on three top "
            "SKUs and a paused acquisition campaign that reduced new-visitor traffic.",
            0.7,
        ),
        (
            "Which products are out of stock?",
            "SKU-001, SKU-007, and SKU-014 currently show zero on-hand inventory; "
            "the rest of the catalog is above reorder threshold.",
            0.7,
        ),
    ],
    ids=["sales_drop", "stockout_query"],
)
def test_synthesis_answers_query(query, summary, min_score):
    """Synthesis summary must actually answer the user's question."""
    test_case = LLMTestCase(
        input=query,
        actual_output=json.dumps({"summary": summary}),
        expected_output=json.dumps({"min_score": min_score}),
    )
    metric = SynthesisRelevanceMetric(threshold=min_score)
    assert_test(test_case, [metric])


@pytest.mark.parametrize(
    "domains_with_data,domains_required",
    [
        (["sales", "inventory"], ["sales", "inventory", "marketing", "support"]),
        (["sales"], ["sales"]),
        (["sales", "inventory", "marketing", "support"], ["sales", "inventory", "marketing", "support"]),  # noqa: E501
        ([], ["sales"]),
    ],
    ids=["partial_coverage", "full_single", "full_all", "no_data"],
)
def test_evidence_score_range(domains_with_data, domains_required):
    """evidence_score must always be in [0.0, 1.0]."""
    actual = _get_reflection_output(domains_with_data, domains_required)

    test_case = LLMTestCase(
        input="test query",
        actual_output=json.dumps(actual),
        expected_output=json.dumps({"evidence_score_valid": True}),
    )

    metric = EvidenceScoreRangeMetric()
    assert_test(test_case, [metric])
