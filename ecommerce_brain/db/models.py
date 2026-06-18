"""SQLAlchemy ORM models: incidents, KEDB, KADB, audit_log.

pgvector column used for semantic search on incident embeddings.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from ecommerce_brain.db.engine import Base
from ecommerce_brain.llm import EMBEDDING_DIM

_EMBEDDING_DIM = EMBEDDING_DIM  # 1536 for text-embedding-3-small


class Incident(Base):
    """Full investigation record — stored post-resolution for future recall."""

    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(50), nullable=False)
    domains_investigated: Mapped[list] = mapped_column(JSONB, default=list)
    root_causes: Mapped[list] = mapped_column(JSONB, default=list)
    evidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    actions_proposed: Mapped[list] = mapped_column(JSONB, default=list)
    actions_approved: Mapped[list] = mapped_column(JSONB, default=list)
    actions_executed: Mapped[list] = mapped_column(JSONB, default=list)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[list | None] = mapped_column(Vector(_EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @classmethod
    def search_similar(
        cls, session: Session, query_embedding: list[float], top_k: int = 3
    ) -> list[Incident]:
        stmt = (
            select(cls)
            .order_by(cls.embedding.cosine_distance(query_embedding))
            .limit(top_k)
        )
        return list(session.scalars(stmt))


class KEDBEntry(Base):
    """Known Error Database — maps symptom patterns to root causes + resolutions."""

    __tablename__ = "kedb"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symptom_summary: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_steps: Mapped[list] = mapped_column(JSONB, default=list)
    affected_domains: Mapped[list] = mapped_column(JSONB, default=list)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    embedding: Mapped[list | None] = mapped_column(Vector(_EMBEDDING_DIM), nullable=True)

    @classmethod
    def search_similar(
        cls, session: Session, query_embedding: list[float], top_k: int = 3
    ) -> list[KEDBEntry]:
        stmt = (
            select(cls)
            .order_by(cls.embedding.cosine_distance(query_embedding))
            .limit(top_k)
        )
        return list(session.scalars(stmt))


class KADBEntry(Base):
    """Known Action Database — tracks action success rates for recommendation scoring."""

    __tablename__ = "kadb"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action_params_template: Mapped[dict] = mapped_column(JSONB, default=dict)
    context_tags: Mapped[list] = mapped_column(JSONB, default=list)
    total_executions: Mapped[int] = mapped_column(Integer, default=0)
    successful_executions: Mapped[int] = mapped_column(Integer, default=0)
    avg_revenue_impact: Mapped[float] = mapped_column(Float, default=0.0)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions


class AuditLog(Base):
    """Append-only audit log — every graph node transition and decision recorded."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    node: Mapped[str] = mapped_column(String(100), nullable=False)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_security_event: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Mock data tables (used by MCP servers — no LLM required, deterministic)

class MockProduct(Base):
    __tablename__ = "mock_products"

    sku: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    current_stock: Mapped[int] = mapped_column(Integer, default=0)
    reorder_point: Mapped[int] = mapped_column(Integer, default=50)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    avg_daily_sales: Mapped[float] = mapped_column(Float, default=0.0)


class MockSalesMetric(Base):
    __tablename__ = "mock_sales_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    aov: Mapped[float] = mapped_column(Float, default=0.0)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)


class MockCampaign(Base):
    __tablename__ = "mock_campaigns"

    campaign_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    daily_budget: Mapped[float] = mapped_column(Float, default=0.0)
    roas: Mapped[float] = mapped_column(Float, default=0.0)
    paused_at: Mapped[str | None] = mapped_column(String(50), nullable=True)


class MockSupportTicket(Base):
    __tablename__ = "mock_support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    issue_type: Mapped[str] = mapped_column(String(100), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.5)
    is_refund: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
