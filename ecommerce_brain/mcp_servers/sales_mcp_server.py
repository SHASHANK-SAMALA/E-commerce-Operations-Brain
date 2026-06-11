import logging

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from ecommerce_brain.tools.sales_tools import (
    get_anomaly_score as _get_anomaly_score,
)
from ecommerce_brain.tools.sales_tools import (
    get_order_breakdown as _get_order_breakdown,
)
from ecommerce_brain.tools.sales_tools import (
    get_revenue_metrics as _get_revenue_metrics,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sales_mcp_server")

mcp = FastMCP("sales-mcp-server", port=8001)

class GetRevenueMetricsInput(BaseModel):
    days: int = Field(default=7, ge=1, le=90, description="Look-back window in days")
    region: str = Field(default="all", description="Region filter or 'all'")

class GetOrderBreakdownInput(BaseModel):
    days: int = Field(default=7, ge=1, le=90)
    group_by: str = Field(default="category", description="'category' or 'region'")

class GetAnomalyScoreInput(BaseModel):
    metric: str = Field(default="revenue", description="'revenue' or 'orders'")
    days: int = Field(default=7, ge=1, le=30)

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
    logger.info("Starting Sales MCP Server on port 8001...")
    mcp.run(transport="sse")
