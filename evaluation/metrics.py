"""Custom DeepEval metrics for the E-Commerce Operations Brain.

These metrics test agent behavior quality — not just "does it run" but
"does it make the right decisions."
"""

from __future__ import annotations

import json

from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase


class CorrectDomainRoutingMetric(BaseMetric):
    """Given a query, did the Coordinator select the right domains?

    A sales-only query must not spawn inventory or support agents.
    False positives waste tokens and money.
    """

    def __init__(self):
        self.threshold = 1.0
        self.score = 0.0
        self.reason = ""

    @property
    def __name__(self):
        return "Correct Domain Routing"

    def measure(self, test_case: LLMTestCase) -> float:
        try:
            actual = json.loads(test_case.actual_output)
            actual_domains = set(actual.get("domains_required", []))
            expected_domains = set(
                json.loads(test_case.expected_output).get("expected_domains", [])
            )

            unexpected = actual_domains - expected_domains
            missing = expected_domains - actual_domains

            self.score = 1.0 if not unexpected and not missing else 0.0
            self.reason = f"unexpected={list(unexpected)}, missing={list(missing)}"
        except (json.JSONDecodeError, KeyError) as e:
            self.score = 0.0
            self.reason = f"Parse error: {e}"
        return self.score

    def is_successful(self) -> bool:
        return self.score >= self.threshold

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)


class CorrectIntentClassificationMetric(BaseMetric):
    """Did the Coordinator classify the intent correctly?

    Intent drives the entire downstream graph topology.
    """

    def __init__(self):
        self.threshold = 1.0
        self.score = 0.0
        self.reason = ""

    @property
    def __name__(self):
        return "Correct Intent Classification"

    def measure(self, test_case: LLMTestCase) -> float:
        try:
            actual = json.loads(test_case.actual_output)
            expected = json.loads(test_case.expected_output)

            actual_intent = actual.get("intent", "")
            expected_intent = expected.get("expected_intent", "")

            self.score = 1.0 if actual_intent == expected_intent else 0.0
            self.reason = f"actual={actual_intent}, expected={expected_intent}"
        except (json.JSONDecodeError, KeyError) as e:
            self.score = 0.0
            self.reason = f"Parse error: {e}"
        return self.score

    def is_successful(self) -> bool:
        return self.score >= self.threshold

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)


class HITLRequiredMetric(BaseMetric):
    """For action-type queries the graph MUST pause at the HITL node.

    Checks that the response carries ``status == 'awaiting_approval'`` when
    ``hitl_required`` is True, and ``status == 'completed'`` otherwise.
    """

    def __init__(self):
        self.threshold = 1.0
        self.score = 0.0
        self.reason = ""

    @property
    def __name__(self):
        return "HITL Required for Actions"

    def measure(self, test_case: LLMTestCase) -> float:
        try:
            actual = json.loads(test_case.actual_output)
            expected = json.loads(test_case.expected_output)

            hitl_required = expected.get("hitl_required", False)
            actual_status = actual.get("status", "")

            if not hitl_required:
                # Non-action queries must complete without pausing.
                self.score = 1.0 if actual_status == "completed" else 0.0
                self.reason = f"Non-HITL query: status={actual_status} (expected 'completed')"
            else:
                # Action queries must pause for human approval.
                self.score = 1.0 if actual_status == "awaiting_approval" else 0.0
                self.reason = f"HITL query: status={actual_status} (expected 'awaiting_approval')"
        except (json.JSONDecodeError, KeyError) as e:
            self.score = 0.0
            self.reason = f"Parse error: {e}"
        return self.score

    def is_successful(self) -> bool:
        return self.score >= self.threshold

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)


class EvidenceScoreRangeMetric(BaseMetric):
    """evidence_score must always be between 0.0 and 1.0.

    Never negative, never > 1. This is a sanity check on the reflection node.
    """

    def __init__(self):
        self.threshold = 1.0
        self.score = 0.0
        self.reason = ""

    @property
    def __name__(self):
        return "Evidence Score in Valid Range"

    def measure(self, test_case: LLMTestCase) -> float:
        try:
            actual = json.loads(test_case.actual_output)
            score = actual.get("evidence_score", -1)

            self.score = 1.0 if 0.0 <= score <= 1.0 else 0.0
            self.reason = f"evidence_score={score}"
        except (json.JSONDecodeError, KeyError) as e:
            self.score = 0.0
            self.reason = f"Parse error: {e}"
        return self.score

    def is_successful(self) -> bool:
        return self.score >= self.threshold

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)


class NoExtraDomainsMetric(BaseMetric):
    """Penalizes routing that spawns unnecessary domain agents.

    Each extra domain costs ~2000 tokens ($0.01-0.03). Routing efficiency
    directly affects cost and latency.
    """

    def __init__(self):
        self.threshold = 0.8
        self.score = 0.0
        self.reason = ""

    @property
    def __name__(self):
        return "No Unnecessary Domains"

    def measure(self, test_case: LLMTestCase) -> float:
        try:
            actual = json.loads(test_case.actual_output)
            expected = json.loads(test_case.expected_output)

            actual_domains = set(actual.get("domains_required", []))
            expected_domains = set(expected.get("expected_domains", []))

            if not expected_domains:
                self.score = 1.0 if not actual_domains else 0.5
                self.reason = f"Expected no domains, got {list(actual_domains)}"
                return self.score

            # Precision: what fraction of actual domains are correct?
            if actual_domains:
                precision = len(actual_domains & expected_domains) / len(actual_domains)
            else:
                precision = 0.0

            self.score = precision
            self.reason = (
                f"Precision={precision:.2f}, actual={list(actual_domains)},"
                f" expected={list(expected_domains)}"
            )
        except (json.JSONDecodeError, KeyError) as e:
            self.score = 0.0
            self.reason = f"Parse error: {e}"
        return self.score

    def is_successful(self) -> bool:
        return self.score >= self.threshold

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)
