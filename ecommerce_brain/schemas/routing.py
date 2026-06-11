"""Routing schemas — validated output of the routing layer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RoutingDecision(BaseModel):
    """Validated output of both rules engine and LLM fallback router.

    The LLM cannot directly control which agents run — it produces this schema
    which is validated by Pydantic before the coordinator acts on it.
    """

    intent: Literal["diagnose", "action", "memory_query", "report"]
    domains_required: list[Literal["sales", "inventory", "marketing", "support"]]
    routing_confidence: float = Field(ge=0.0, le=1.0)
    routing_source: Literal["rules_engine", "llm_fallback"] = "rules_engine"
    matched_rule: str | None = None
