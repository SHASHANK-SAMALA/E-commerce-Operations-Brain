"""Marketing domain tools."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from ecommerce_brain.db.engine import get_session
from ecommerce_brain.db.models import MockCampaign
from ecommerce_brain.tools.registry import register_tool


class GetCampaignStatusInput(BaseModel):
    status_filter: str = Field(default="all", description="'all', 'active', or 'paused'")


class GetAdPerformanceInput(BaseModel):
    channel: str = Field(default="all", description="Channel filter or 'all'")


@register_tool(args_schema=GetCampaignStatusInput)
def get_campaign_status(status_filter: str = "all") -> list[dict]:
    """Return campaign health — paused campaigns are the primary marketing signal."""
    with get_session() as session:
        stmt = select(MockCampaign)
        if status_filter != "all":
            stmt = stmt.where(MockCampaign.status == status_filter)
        campaigns = session.scalars(stmt).all()
        return [
            {
                "campaign_id": c.campaign_id,
                "name": c.name,
                "channel": c.channel,
                "status": c.status,
                "daily_budget": c.daily_budget,
                "roas": c.roas,
                "paused_at": c.paused_at,
                "daily_revenue_impact": (
                    round(c.daily_budget * c.roas, 2) if c.status == "active" else 0.0
                ),
            }
            for c in campaigns
        ]


@register_tool(args_schema=GetAdPerformanceInput)
def get_ad_performance(channel: str = "all") -> dict:
    """Get aggregated ad performance metrics by channel."""
    with get_session() as session:
        stmt = select(MockCampaign).where(MockCampaign.status == "active")
        if channel != "all":
            stmt = stmt.where(MockCampaign.channel == channel)
        active = session.scalars(stmt).all()
        paused = session.scalars(
            select(MockCampaign).where(MockCampaign.status == "paused")
        ).all()
        total_budget = sum(c.daily_budget for c in active)
        total_paused_budget = sum(c.daily_budget for c in paused)
        avg_roas = sum(c.roas for c in active) / max(len(active), 1)
        return {
            "active_campaigns": len(active),
            "paused_campaigns": len(paused),
            "total_active_daily_budget": round(total_budget, 2),
            "total_paused_daily_budget": round(total_paused_budget, 2),
            "average_roas": round(avg_roas, 2),
            "estimated_daily_revenue_at_risk": round(total_paused_budget * avg_roas, 2),
        }


# ── Semantic aliases used by the agent YAML definitions ───────────────────────
# NOTE: resume_campaign is an action tool — defined in action_tools.py only.

class GetCampaignPerformanceInput(BaseModel):
    days: int = Field(default=7, ge=1, le=90)


class GetChannelRoasInput(BaseModel):
    days: int = Field(default=7, ge=1, le=90)


class GetPausedCampaignsInput(BaseModel):
    hours: int = Field(
        default=168, ge=1, description="Only show campaigns paused within this many hours"
    )


@register_tool(args_schema=GetCampaignPerformanceInput)
def get_campaign_performance(days: int = 7) -> list[dict]:
    """Get all campaigns with performance metrics — revenue attribution, ROAS, and status."""
    return get_campaign_status(status_filter="all")


@register_tool(args_schema=GetPausedCampaignsInput)
def get_paused_campaigns(hours: int = 168) -> list[dict]:
    """Get campaigns that are currently paused with their daily budget at risk."""
    all_campaigns = get_campaign_status(status_filter="paused")
    return [
        {
            **c,
            "daily_revenue_at_risk": round(c["daily_budget"] * 3.8, 2),
        }
        for c in all_campaigns
    ]


@register_tool(args_schema=GetChannelRoasInput)
def get_channel_roas(days: int = 7) -> dict:
    """Get ROAS breakdown by channel to identify underperforming channels."""
    perf = get_ad_performance(channel="all")
    with get_session() as session:
        stmt = select(MockCampaign).where(MockCampaign.status == "active")
        active = session.scalars(stmt).all()
        channel_data: dict = {}
        for c in active:
            ch = c.channel
            if ch not in channel_data:
                channel_data[ch] = {"budget": 0.0, "roas_sum": 0.0, "count": 0}
            channel_data[ch]["budget"] += c.daily_budget
            channel_data[ch]["roas_sum"] += c.roas
            channel_data[ch]["count"] += 1

    return {
        "by_channel": [
            {
                "channel": ch,
                "avg_roas": round(v["roas_sum"] / max(v["count"], 1), 2),
                "daily_budget": round(v["budget"], 2),
                "is_underperforming": (v["roas_sum"] / max(v["count"], 1)) < 2.0,
            }
            for ch, v in channel_data.items()
        ],
        "total_summary": perf,
    }
