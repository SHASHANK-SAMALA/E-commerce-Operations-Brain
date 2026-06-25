"""LangGraph GraphState — all fields in one TypedDict.

Uses Annotated[list, operator.add] for append-only audit_log.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from ecommerce_brain.schemas.memory import MemoryContext
from ecommerce_brain.schemas.outputs import (
    InventoryReport,
    MarketingReport,
    ReflectionResult,
    RootCauseReport,
    SalesReport,
    SupportReport,
)
from ecommerce_brain.schemas.routing import RoutingDecision


class ActionState(TypedDict):
    """In-graph proposed action record — lightweight TypedDict for state passage.

    The full API-facing model is schemas.outputs.ProposedAction (Pydantic).
    """

    action_id: str
    action_type: str
    params: dict[str, Any]
    estimated_impact: str
    dry_run_result: str | None
    kadb_success_rate: float | None


class ExecutionState(TypedDict):
    """In-graph execution record — lightweight TypedDict for state passage.

    The full API-facing result is schemas.outputs.ExecutionResult (Pydantic).
    """

    action_id: str
    success: bool
    message: str


class GraphState(TypedDict):
    """Full mutable state threaded through every graph node.

    Append-only fields use ``Annotated[list, operator.add]`` so parallel fan-out
    nodes can each write without clobbering each other's entries.
    """

    # Request
    query: str
    query_id: str
    session_id: str | None

    # Routing
    routing_decision: RoutingDecision | None
    intent: str | None
    domains_required: list[str]
    routing_confidence: float

    # Memory
    memory_context: MemoryContext | None

    # Domain reports (fan-in from parallel agents)
    sales_report: SalesReport | None
    inventory_report: InventoryReport | None
    marketing_report: MarketingReport | None
    support_report: SupportReport | None

    # Reflection
    reflection_result: ReflectionResult | None
    loop_count: int

    # Synthesis
    root_cause_report: RootCauseReport | None
    proposed_actions: list[ActionState]

    # HITL — "pending" | "pending_approval" | "approved" | "rejected"
    hitl_status: str
    # Set True by paths that never need human approval (e.g. memory_query).
    # Checked by _hitl_edge in graph.py to skip the interrupt call entirely.
    skip_hitl: bool
    approved_actions: list[ActionState]

    # Execution
    execution_results: list[ExecutionState]

    # Telemetry
    investigation_start_ms: int
    total_tokens: int

    # Error / security — reducer merges concurrent writes from parallel agents
    error: Annotated[str | None, lambda a, b: "\n".join(filter(None, [a, b])) or None]
    blocked_reason: str | None

    # Audit log (append-only)
    audit_log: Annotated[list[dict], operator.add]
