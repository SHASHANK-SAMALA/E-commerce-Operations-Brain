"""Support domain tools."""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ecommerce_brain.db.engine import get_session
from ecommerce_brain.db.models import MockSupportTicket
from ecommerce_brain.tools.registry import register_tool


class GetComplaintVolumeInput(BaseModel):
    days: int = Field(default=7, ge=1, le=60)


class GetRefundRateInput(BaseModel):
    days: int = Field(default=7, ge=1, le=60)


class GetCommonIssuesInput(BaseModel):
    days: int = Field(default=7, ge=1, le=60)
    top_n: int = Field(default=5, ge=1, le=20)


@register_tool(args_schema=GetComplaintVolumeInput)
def get_complaint_volume(days: int = 7) -> dict:
    """Get complaint volume for current period vs prior period."""
    today = date.today()
    start = today - timedelta(days=days)
    prior_start = start - timedelta(days=days)

    with get_session() as session:
        def _count(d_from: date, d_to: date) -> int:
            return session.scalar(
                select(func.count()).where(
                    MockSupportTicket.date >= d_from.isoformat(),
                    MockSupportTicket.date < d_to.isoformat(),
                )
            ) or 0

        cur = _count(start, today)
        prior = _count(prior_start, start)

    delta_pct = ((cur - prior) / max(prior, 1)) * 100
    return {
        "period_days": days,
        "current_count": cur,
        "prior_count": prior,
        "delta_pct": round(delta_pct, 2),
        "is_spike": delta_pct > 25,
    }


@register_tool(args_schema=GetRefundRateInput)
def get_refund_rate(days: int = 7) -> dict:
    """Get refund rate and top SKUs driving refunds."""
    today = date.today()
    start = today - timedelta(days=days)

    with get_session() as session:
        total = session.scalar(
            select(func.count()).where(MockSupportTicket.date >= start.isoformat())
        ) or 0
        refunds = session.scalar(
            select(func.count()).where(
                MockSupportTicket.date >= start.isoformat(),
                MockSupportTicket.is_refund.is_(True),
            )
        ) or 0

        # Top SKUs with refunds
        top_skus = session.execute(
            select(MockSupportTicket.sku, func.count().label("cnt"))
            .where(
                MockSupportTicket.date >= start.isoformat(),
                MockSupportTicket.is_refund.is_(True),
                MockSupportTicket.sku.isnot(None),
            )
            .group_by(MockSupportTicket.sku)
            .order_by(func.count().desc())
            .limit(5)
        ).all()

    return {
        "period_days": days,
        "refund_rate_pct": round((refunds / max(total, 1)) * 100, 2),
        "total_tickets": total,
        "refund_tickets": refunds,
        "top_refund_skus": [{"sku": r[0], "count": r[1]} for r in top_skus],
    }


@register_tool(args_schema=GetCommonIssuesInput)
def get_common_issues(days: int = 7, top_n: int = 5) -> list[dict]:
    """Cluster support tickets by issue type and return top N."""
    today = date.today()
    start = today - timedelta(days=days)

    with get_session() as session:
        rows = session.execute(
            select(
                MockSupportTicket.issue_type,
                func.count().label("count"),
                func.avg(MockSupportTicket.sentiment_score).label("avg_sentiment"),
            )
            .where(MockSupportTicket.date >= start.isoformat())
            .group_by(MockSupportTicket.issue_type)
            .order_by(func.count().desc())
            .limit(top_n)
        ).all()

        # Sample ticket per issue type
        examples = {}
        for issue_type, _, _ in rows:
            ticket = session.scalar(
                select(MockSupportTicket.summary).where(
                    MockSupportTicket.date >= start.isoformat(),
                    MockSupportTicket.issue_type == issue_type,
                ).limit(1)
            )
            examples[issue_type] = ticket or ""

    return [
        {
            "issue_type": r[0],
            "count": r[1],
            "avg_sentiment": round(float(r[2] or 0.5), 2),
            "example_ticket": examples.get(r[0], ""),
        }
        for r in rows
    ]


@register_tool(args_schema=GetComplaintVolumeInput)
def get_review_sentiment(days: int = 7) -> dict:
    """Average sentiment score and negative ticket percentage."""
    today = date.today()
    start = today - timedelta(days=days)

    with get_session() as session:
        result = session.execute(
            select(
                func.avg(MockSupportTicket.sentiment_score),
                func.count(),
            ).where(MockSupportTicket.date >= start.isoformat())
        ).one()

        negative_count = session.scalar(
            select(func.count()).where(
                MockSupportTicket.date >= start.isoformat(),
                MockSupportTicket.sentiment_score < 0.35,
            )
        ) or 0

    avg_score = float(result[0] or 0.5)
    total = int(result[1] or 0)
    return {
        "avg_sentiment_score": round(avg_score, 3),
        "total_tickets_analysed": total,
        "negative_pct": round((negative_count / max(total, 1)) * 100, 2),
        "sentiment_trend": (
            "DECLINING" if avg_score < 0.35 else ("NEUTRAL" if avg_score < 0.6 else "POSITIVE")
        ),
    }


class GetComplaintTrendsInput(BaseModel):
    days: int = Field(default=14, ge=1, le=60)


@register_tool(args_schema=GetComplaintTrendsInput)
def get_complaint_trends(days: int = 14) -> list[dict]:
    """Get daily complaint volume trend broken down by issue type for the last N days."""
    today = date.today()
    start = today - timedelta(days=days)

    with get_session() as session:
        rows = session.execute(
            select(
                MockSupportTicket.date,
                MockSupportTicket.issue_type,
                func.count().label("count"),
            )
            .where(MockSupportTicket.date >= start.isoformat())
            .group_by(MockSupportTicket.date, MockSupportTicket.issue_type)
            .order_by(MockSupportTicket.date)
        ).all()

    daily: dict = {}
    for row in rows:
        d = str(row[0])
        if d not in daily:
            daily[d] = {"date": d, "total": 0, "by_issue": {}}
        daily[d]["by_issue"][row[1]] = row[2]
        daily[d]["total"] += row[2]

    return list(daily.values())

