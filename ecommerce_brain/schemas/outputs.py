"""Pydantic output schemas — every agent boundary uses these, never raw strings.

Memory context (MemoryContext, SimilarIncident) live in schemas/memory.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ── Stockout (used in InventoryReport) ────────────────────────────────────────
class StockoutItem(BaseModel):
    sku: str
    name: str
    time_oos_hours: float
    impressions_lost: int
    suggested_restock_qty: int


# ── Category revenue (used in SalesReport) ────────────────────────────────────
class CategoryRevenue(BaseModel):
    """A declining product category with its revenue figure.

    The field_validator on SalesReport handles str → CategoryRevenue coercion
    before Pydantic validates the list items.
    """

    category: str
    revenue: float | None = None
    delta_pct: float | None = None

# ── Issue cluster (used in SupportReport) ─────────────────────────────────────
class IssueCluster(BaseModel):
    issue_type: str
    count: int
    example_ticket: str


# ── Campaign item (used in MarketingReport) ───────────────────────────────────
class CampaignItem(BaseModel):
    campaign_id: str
    name: str
    channel: str
    paused_at: datetime | None = None
    daily_budget: float


# ── Domain reports ─────────────────────────────────────────────────────────────
class SalesReport(BaseModel):
    domain: Literal["sales"] = "sales"
    revenue_delta_pct: float  # -0.20 = -20%
    order_delta_pct: float
    aov_delta_pct: float
    affected_regions: list[str]
    top_declining_categories: list[CategoryRevenue] = Field(default_factory=list)
    anomaly_score: float = Field(ge=0.0, le=1.0)
    is_drop_significant: bool
    date_range: str
    raw_metrics: dict = Field(default_factory=dict)

    @field_validator("top_declining_categories", mode="before")
    @classmethod
    def _coerce_top_declining_categories(cls, value):
        if not isinstance(value, list):
            return value
        coerced = []
        for item in value:
            if isinstance(item, str):
                coerced.append({"category": item})
            else:
                coerced.append(item)
        return coerced

    @property
    def top_declining_category_names(self) -> list[str]:
        """Convenience accessor — returns just the category name strings."""
        return [c.category for c in self.top_declining_categories]


class InventoryReport(BaseModel):
    domain: Literal["inventory"] = "inventory"
    stockouts: list[StockoutItem] = Field(default_factory=list)
    near_stockout_skus: list[str] = Field(default_factory=list)
    revenue_impact_estimate: float = 0.0
    restock_urgency: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = "LOW"
    top_affected_skus: list[str] = Field(default_factory=list)
    cart_abandonment_spike: bool = False


class MarketingReport(BaseModel):
    domain: Literal["marketing"] = "marketing"
    paused_campaigns: list[CampaignItem] = Field(default_factory=list)
    underperforming_channels: list[str] = Field(default_factory=list)
    missed_promotions: list[str] = Field(default_factory=list)
    roas_delta_pct: float = 0.0
    total_paused_spend: float = 0.0


class SupportReport(BaseModel):
    domain: Literal["support"] = "support"
    complaint_spike: bool = False
    complaint_delta_pct: float = 0.0
    refund_rate_delta_pct: float = 0.0
    sentiment_score: float = Field(ge=0.0, le=1.0, default=0.5)
    top_issues: list[IssueCluster] = Field(default_factory=list)
    top_refund_skus: list[str] = Field(default_factory=list)


# ── Reflection output ─────────────────────────────────────────────────────────
class ReflectionResult(BaseModel):
    domains_checked: list[str]
    domains_with_data: list[str]
    domains_missing: list[str]
    evidence_score: float = Field(ge=0.0, le=1.0)  # measurable, not "LLM confidence"
    gaps: list[str] = Field(default_factory=list)
    should_reinvestigate: bool = False
    reinvestigate_domains: list[str] = Field(default_factory=list)


# ── Root cause report ─────────────────────────────────────────────────────────
class RootCause(BaseModel):
    cause: str
    domain: str
    evidence: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]


class ProposedAction(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    action_type: str
    description: str
    parameters: dict
    estimated_cost: float | None = None
    estimated_impact: str | None = None
    historical_success_rate: float | None = None  # from KADB


class RootCauseReport(BaseModel):
    query_id: str
    query: str
    root_causes: list[RootCause]
    evidence_score: float = Field(ge=0.0, le=1.0)
    summary: str
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    domains_analyzed: list[str]
    similar_past_incidents: list[str] = Field(default_factory=list)
    investigation_duration_ms: int
    total_tokens_used: int
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Action execution ───────────────────────────────────────────────────────────
class ExecutionResult(BaseModel):
    action_id: str
    action_type: str
    success: bool
    message: str
    dry_run: bool = False
    executed_at: datetime | None = None


# ── Audit ─────────────────────────────────────────────────────────────────────
class AuditEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    node: str
    event: str
    details: dict = Field(default_factory=dict)
