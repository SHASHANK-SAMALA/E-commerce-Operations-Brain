"""Marketing MCP server — exposes marketing domain tools over SSE transport."""

import structlog
from mcp.server.fastmcp import FastMCP

from ecommerce_brain.tools.marketing_tools import get_ad_performance as _get_ad_performance
from ecommerce_brain.tools.marketing_tools import get_campaign_status as _get_campaign_status
from ecommerce_brain.tools.marketing_tools import get_channel_roas as _get_channel_roas
from ecommerce_brain.tools.marketing_tools import get_paused_campaigns as _get_paused_campaigns

log = structlog.get_logger(__name__)

mcp = FastMCP("marketing-mcp-server", port=8003, host="0.0.0.0")  # nosec B104


@mcp.tool()
def get_campaign_status(status_filter: str = "all") -> list[dict]:
    """Return campaign health — paused campaigns are the primary marketing signal."""
    return _get_campaign_status(status_filter=status_filter)


@mcp.tool()
def get_ad_performance(channel: str = "all") -> dict:
    """Get aggregated ad performance metrics by channel."""
    return _get_ad_performance(channel=channel)


@mcp.tool()
def get_paused_campaigns(hours: int = 168) -> list[dict]:
    """Get campaigns that are currently paused with their daily budget at risk."""
    return _get_paused_campaigns(hours=hours)


@mcp.tool()
def get_channel_roas(days: int = 7) -> dict:
    """Get ROAS breakdown by channel to identify underperforming channels."""
    return _get_channel_roas(days=days)


if __name__ == "__main__":
    log.info("mcp_server.starting", server="marketing", port=8003)
    mcp.run(transport="sse")
