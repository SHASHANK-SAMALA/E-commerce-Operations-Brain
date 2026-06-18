import logging

from mcp.server.fastmcp import FastMCP

from ecommerce_brain.tools.support_tools import (
    get_common_issues as _get_common_issues,
)
from ecommerce_brain.tools.support_tools import (
    get_complaint_volume as _get_complaint_volume,
)
from ecommerce_brain.tools.support_tools import (
    get_refund_rate as _get_refund_rate,
)
from ecommerce_brain.tools.support_tools import (
    get_review_sentiment as _get_review_sentiment,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("support_mcp_server")

mcp = FastMCP("support-mcp-server", port=8004, host="0.0.0.0")

@mcp.tool()
def get_complaint_volume(days: int = 7) -> dict:
    """Get complaint volume for current period vs prior period."""
    return _get_complaint_volume(days=days)

@mcp.tool()
def get_refund_rate(days: int = 7) -> dict:
    """Get refund rate and top SKUs driving refunds."""
    return _get_refund_rate(days=days)

@mcp.tool()
def get_common_issues(days: int = 7, top_n: int = 5) -> list[dict]:
    """Cluster support tickets by issue type and return top N."""
    return _get_common_issues(days=days, top_n=top_n)

@mcp.tool()
def get_review_sentiment(days: int = 7) -> dict:
    """Average sentiment score and negative ticket percentage."""
    return _get_review_sentiment(days=days)

if __name__ == "__main__":
    logger.info("Starting Support MCP Server on port 8004...")
    mcp.run(transport="sse")
