"""Inventory MCP server — exposes inventory domain tools over SSE transport."""

import structlog
from mcp.server.fastmcp import FastMCP

from ecommerce_brain.tools.inventory_tools import get_restock_candidates as _get_restock_candidates
from ecommerce_brain.tools.inventory_tools import get_stock_levels as _get_stock_levels
from ecommerce_brain.tools.inventory_tools import get_stockout_products as _get_stockout_products

log = structlog.get_logger(__name__)

mcp = FastMCP("inventory-mcp-server", port=8002, host="0.0.0.0")  # nosec B104

@mcp.tool()
def get_stock_levels(skus: list[str] | None = None) -> list[dict]:
    """Get current stock levels, reorder points, and days-of-supply for products."""
    return _get_stock_levels(skus=skus)

@mcp.tool()
def get_stockout_products(include_near_stockout: bool = True) -> dict:
    """Return products currently out-of-stock and near-stockout SKUs."""
    return _get_stockout_products(include_near_stockout=include_near_stockout)

@mcp.tool()
def get_restock_candidates(top_n: int = 10) -> list[dict]:
    """Return top restock candidates sorted by urgency (revenue impact)."""
    return _get_restock_candidates(top_n=top_n)

if __name__ == "__main__":
    log.info("mcp_server.starting", server="inventory", port=8002)
    mcp.run(transport="sse")
