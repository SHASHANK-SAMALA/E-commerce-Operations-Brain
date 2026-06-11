"""Tests for synthesis action gating and output shaping."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from ecommerce_brain.graph.nodes.synthesis import synthesis_node
from ecommerce_brain.schemas.outputs import ProposedAction, RootCause, RootCauseReport


class _FakeStructuredLLM:
    def __init__(self, report: RootCauseReport):
        self._report = report

    async def ainvoke(self, _messages):
        return self._report


class _FakeLLM:
    def __init__(self, report: RootCauseReport):
        self._report = report

    def with_structured_output(self, _schema, method="function_calling"):
        return _FakeStructuredLLM(self._report)


def _make_report(action_type: str = "increase_campaign_budget") -> RootCauseReport:
    return RootCauseReport(
        query_id="inv-test123",
        query="Test query",
        root_causes=[
            RootCause(
                cause="Campaign underdelivery",
                domain="marketing",
                evidence="ROAS down 12%",
                confidence="HIGH",
            )
        ],
        evidence_score=0.82,
        summary="Marketing underperformed and likely reduced traffic quality.",
        proposed_actions=[
            ProposedAction(
                action_id="act-1",
                action_type=action_type,
                description="Increase budget",
                parameters={"campaign_id": "CAM-001", "increase_pct": 20.0},
                estimated_impact="Recover traffic",
            )
        ],
        domains_analyzed=["marketing"],
        similar_past_incidents=[],
        investigation_duration_ms=100,
        total_tokens_used=10,
        generated_at=datetime.utcnow(),
    )


def _make_state(intent: str) -> dict:
    return {
        "query": "Why did sales drop yesterday?",
        "query_id": "inv-test123",
        "intent": intent,
        "reflection_result": None,
        "memory_context": None,
        "sales_report": None,
        "inventory_report": None,
        "marketing_report": None,
        "support_report": None,
        "investigation_start_ms": 1700000000000,
    }


@pytest.mark.asyncio
async def test_synthesis_suppresses_actions_for_non_action_intent():
    report = _make_report()

    with (
        patch("ecommerce_brain.graph.nodes.synthesis.synthesis_llm", return_value=_FakeLLM(report)),
        patch("ecommerce_brain.graph.nodes.synthesis.get_action_stats", return_value={"success_rate": 0.7}),
    ):
        result = await synthesis_node(_make_state("diagnose"))

    assert result.get("error") is None
    assert result["proposed_actions"] == []
    assert result["root_cause_report"].proposed_actions == []


@pytest.mark.asyncio
async def test_synthesis_keeps_actions_for_action_intent():
    report = _make_report()

    with (
        patch("ecommerce_brain.graph.nodes.synthesis.synthesis_llm", return_value=_FakeLLM(report)),
        patch("ecommerce_brain.graph.nodes.synthesis.get_action_stats", return_value={"success_rate": 0.7}),
    ):
        result = await synthesis_node(_make_state("action"))

    assert result.get("error") is None
    assert len(result["proposed_actions"]) == 1
    assert result["proposed_actions"][0]["action_type"] == "increase_campaign_budget"
