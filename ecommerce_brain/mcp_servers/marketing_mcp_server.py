import logging

from mcp.server.fastmcp import FastMCP

from ecommerce_brain.tools.marketing_tools import (
    get_ad_performance as _get_ad_performance,
)
from ecommerce_brain.tools.marketing_tools import (
    get_campaign_status as _get_campaign_status,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("marketing_mcp_server")

mcp = FastMCP("marketing-mcp-server", port=8003, host="0.0.0.0")  # nosec B104

@mcp.tool()
def get_campaign_status(status_filter: str = "all") -> list[dict]:
    """Return campaign health — paused campaigns are the primary marketing signal."""
    return _get_campaign_status(status_filter=status_filter)

@mcp.tool()
def get_ad_performance(channel: str = "all") -> dict:
    """Get aggregated ad performance metrics by channel."""
    return _get_ad_performance(channel=channel)

if __name__ == "__main__":
    logger.info("Starting Marketing MCP Server on port 8003...")
    mcp.run(transport="sse")
