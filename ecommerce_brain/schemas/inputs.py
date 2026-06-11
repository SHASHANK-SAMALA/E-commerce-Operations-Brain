"""Input schemas for API endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class InvestigateRequest(BaseModel):
    query: str = Field(
        min_length=1, max_length=2000, description="Business question or problem statement"
    )
    session_id: str | None = Field(default=None, description="Optional session continuity ID")


class HITLDecision(BaseModel):
    approved: bool
    approved_action_ids: list[str] | None = Field(
        default=None, description="Specific action IDs to approve. None = approve all."
    )
    rejection_reason: str | None = Field(default=None, max_length=500)
