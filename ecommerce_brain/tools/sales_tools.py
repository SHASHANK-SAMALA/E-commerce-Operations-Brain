"""Sales domain tools — backed by mock DB, no LLM involved."""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ecommerce_brain.db.engine import get_session
from ecommerce_brain.db.models import MockSalesMetric
from ecommerce_brain.tools.registry import register_tool


class GetRevenueMetricsInput(BaseModel):
    days: int = Field(default=7, ge=1, le=90, description="Look-back window in days")
    region: str = Field(default="all", description="Region filter or 'all'")


class GetOrderBreakdownInput(BaseModel):
    days: int = Field(default=7, ge=1, le=90)
    group_by: str = Field(default="category", description="'category' or 'region'")


class GetAnomalyScoreInput(BaseModel):
    metric: str = Field(default="revenue", description="'revenue' or 'orders'")
    days: int = Field(default=7, ge=1, le=30)


@register_tool(args_schema=GetRevenueMetricsInput)
def get_revenue_metrics(days: int = 7, region: str = "all") -> dict:
    """Get aggregated revenue, orders, and AOV for a date range vs prior period."""
    today = date.today()
    start = today - timedelta(days=days)
    prior_start = start - timedelta(days=days)

    with get_session() as session:
        def _query(d_from: date, d_to: date) -> tuple[float, int]:
            stmt = select(func.sum(MockSalesMetric.revenue), func.sum(MockSalesMetric.orders))
            stmt = stmt.where(
                MockSalesMetric.date >= d_from.isoformat(),
                MockSalesMetric.date < d_to.isoformat(),
            )
            if region != "all":
                stmt = stmt.where(MockSalesMetric.region == region)
            row = session.execute(stmt).one()
            return float(row[0] or 0), int(row[1] or 0)

        cur_rev, cur_ord = _query(start, today)
        pri_rev, pri_ord = _query(prior_start, start)

    rev_delta = (cur_rev - pri_rev) / max(pri_rev, 1)
    ord_delta = (cur_ord - pri_ord) / max(pri_ord, 1)
    cur_aov = cur_rev / max(cur_ord, 1)
    pri_aov = pri_rev / max(pri_ord, 1)

    return {
        "period_days": days,
        "region": region,
        "revenue": round(cur_rev, 2),
        "revenue_delta_pct": round(rev_delta * 100, 2),
        "orders": cur_ord,
        "order_delta_pct": round(ord_delta * 100, 2),
        "aov": round(cur_aov, 2),
        "aov_delta_pct": round(((cur_aov - pri_aov) / max(pri_aov, 1)) * 100, 2),
    }


@register_tool(args_schema=GetOrderBreakdownInput)
def get_order_breakdown(days: int = 7, group_by: str = "category") -> list[dict]:
    """Get order/revenue breakdown grouped by category or region."""
    today = date.today()
    start = today - timedelta(days=days)

    with get_session() as session:
        col = MockSalesMetric.category if group_by == "category" else MockSalesMetric.region
        stmt = (
            select(col, func.sum(MockSalesMetric.revenue), func.sum(MockSalesMetric.orders))
            .where(MockSalesMetric.date >= start.isoformat())
            .group_by(col)
            .order_by(func.sum(MockSalesMetric.revenue).desc())
        )
        rows = session.execute(stmt).all()

    return [
        {"group": r[0], "revenue": round(float(r[1] or 0), 2), "orders": int(r[2] or 0)}
        for r in rows
    ]


@register_tool(args_schema=GetAnomalyScoreInput)
def get_anomaly_score(metric: str = "revenue", days: int = 7) -> dict:
    """Compute z-score anomaly for the latest day vs rolling mean."""
    today = date.today()
    window_start = today - timedelta(days=days + 14)

    with get_session() as session:
        col = MockSalesMetric.revenue if metric == "revenue" else MockSalesMetric.orders
        stmt = (
            select(MockSalesMetric.date, func.sum(col).label("val"))
            .where(MockSalesMetric.date >= window_start.isoformat())
            .group_by(MockSalesMetric.date)
            .order_by(MockSalesMetric.date)
        )
        rows = session.execute(stmt).all()

    if len(rows) < 3:
        return {"metric": metric, "anomaly_score": 0.0, "is_anomaly": False, "zscore": 0.0}

    values = [float(r[1]) for r in rows]
    baseline = values[:-days]
    recent = values[-days:]

    import statistics
    mean = statistics.mean(baseline)
    stdev = statistics.stdev(baseline) or 1.0
    latest = statistics.mean(recent)
    zscore = (latest - mean) / stdev
    anomaly_score = min(1.0, abs(zscore) / 4.0)

    return {
        "metric": metric,
        "anomaly_score": round(anomaly_score, 3),
        "is_anomaly": abs(zscore) > 2.0,
        "zscore": round(zscore, 3),
        "baseline_mean": round(mean, 2),
        "recent_mean": round(latest, 2),
    }
