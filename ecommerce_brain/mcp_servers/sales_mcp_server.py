"""Sales MCP server — exposes sales domain tools over SSE transport."""

import structlog
from mcp.server.fastmcp import FastMCP

from ecommerce_brain.tools.sales_tools import get_anomaly_score as _get_anomaly_score
from ecommerce_brain.tools.sales_tools import get_order_breakdown as _get_order_breakdown
from ecommerce_brain.tools.sales_tools import get_revenue_metrics as _get_revenue_metrics

log = structlog.get_logger(__name__)

mcp = FastMCP("sales-mcp-server", port=8001, host="0.0.0.0")  # nosec B104

@mcp.tool()
def get_revenue_metrics(days: int = 7, region: str = "all") -> dict:
    """Get aggregated revenue, orders, and AOV for a date range vs prior period."""
    return _get_revenue_metrics(days=days, region=region)

@mcp.tool()
def get_order_breakdown(days: int = 7, group_by: str = "category") -> list[dict]:
    """Get order/revenue breakdown grouped by category or region."""
    return _get_order_breakdown(days=days, group_by=group_by)

@mcp.tool()
def get_anomaly_score(metric: str = "revenue", days: int = 7) -> dict:
    """Compute z-score anomaly for the latest day vs rolling mean."""
    return _get_anomaly_score(metric=metric, days=days)

if __name__ == "__main__":
    log.info("mcp_server.starting", server="sales", port=8001)
    mcp.run(transport="sse")
